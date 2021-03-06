import traceback

from .metadata_sources.skip_episode import SkipEpisode
from . import metadata_sources
from .episode_source import EpisodeSource
from . import Show
from .show_source import ShowSource
from . import NoEpisodesError, NoSuchShowError
from .metadata_sources.skip_show import SkipShow
from . import settings as SETTINGS
import requests

from cached_property import cached_property

import sys
import re


class PodcastFeedGenerator:

    def __init__(self, pretty_xml=False, quiet=False):
        self.requests = requests.Session()
        self.requests.headers.update({"User-Agent": "podcast-feed-gen"})

        self.show_source = ShowSource(self.requests)
        self.pretty_xml = pretty_xml
        self.re_remove_chars = re.compile(r"[^\w\d]|_")

        SETTINGS.QUIET = quiet

    @staticmethod
    def register_redirect_services(sound_redirect, article_redirect):
        SETTINGS.URL_REDIRECTION_SOUND_URL = sound_redirect
        SETTINGS.URL_REDIRECTION_ARTICLE_URL = article_redirect

    @cached_property
    def episode_metadata_sources(self):
        # Instantiate them
        return [
            source(
                SETTINGS.METADATA_SOURCE.get(source.__name__, dict()),
                SETTINGS.BYPASS_EPISODE.get(source.__name__, set()),
                self.requests
            )
            for source in metadata_sources.EPISODE_METADATA_SOURCES
        ]

    @cached_property
    def show_metadata_sources(self):
        # Instantiate them
        return [
            source(
                SETTINGS.METADATA_SOURCE.get(source.__name__, dict()),
                SETTINGS.BYPASS_SHOW.get(source.__name__, set()),
                self.requests
            )
            for source in metadata_sources.SHOW_METADATA_SOURCES
        ]

    def generate_feed(self, show_id: int, force: bool =True) -> bytes:
        """Generate RSS feed for the show represented by the given show_id.

        Args:
            show_id (int): DigAS ID for the show.
            force (bool): Set to False to throw NoEpisodesError if there are no episodes for the given show.
                Set to True to just generate the feed with no episodes in such cases.

        Returns:
            str: The RSS podcast feed for the given show_id.
        """
        try:
            show = self.show_source.shows[show_id]
        except KeyError as e:
            raise NoSuchShowError from e

        return self._generate_feed(show, skip_empty=not force, enable_skip_show=not force)

    def _generate_feed(self, show: Show, skip_empty: bool =True, enable_skip_show: bool =True,
                       episode_source: EpisodeSource =None) -> bytes:
        """Generate RSS feed for the provided show.

        This differs from generate_feed in that it accept Show, not show_id, as argument.

        Args:
            show (Show): The show which shall have its podcast feed generated. Its metadata will be filled by metadata
                sources.
            skip_empty (bool): Set to true to raise exception if there are no episodes for this show.
            enable_skip_show (bool): Skip this show if any Show Metadata source raises SkipShow.
            episode_source (EpisodeSource): The EpisodeSource which will be used.
                A new one will be created if not given.

        Returns:
            str: The RSS podcast feed for the given show.
        """

        # Populate show with more metadata
        if not SETTINGS.QUIET:
            print("Finding show metadata...", end="\r", file=sys.stderr)
        self._populate_show_metadata(show, enable_skip_show)

        # Start generating feed
        feed = show.init_feed()

        # Add episodes
        if not episode_source:
            episode_source = EpisodeSource(self.requests)
        try:
            episode_source.episode_list(show)
        except NoEpisodesError as e:
            if skip_empty:
                raise e
            else:
                # Go on and generate empty feed
                pass
        show.add_episodes_to_feed(episode_source, self.episode_metadata_sources)

        # Generate!
        return feed.rss_str(pretty=self.pretty_xml)

    def generate_all_feeds_sequence(self) -> dict:
        return self.generate_feeds_sequence(self.show_source.shows.values())

    def generate_feeds_sequence(self, shows) -> dict:
        """Generate RSS feeds for all known shows, one at a time."""
        # Prepare for progress bar
        num_shows = len(shows)
        i = 0

        # Ensure we only download list of episodes once
        if not SETTINGS.QUIET:
            print("Downloading metadata, this could take a while...", file=sys.stderr)
        es = EpisodeSource(self.requests)
        self._prepare_for_batch(es)

        feeds = dict()
        for show in shows:
            if not SETTINGS.QUIET:
                # Update progress bar
                i += 1
                print("{0: <60} ({1:03}/{2:03})".format(show.title, i, num_shows),
                      file=sys.stderr)
            try:
                # Do the job
                feeds[show.show_id] = self._generate_feed(show, episode_source=es)
            except (NoEpisodesError, SkipShow):
                # Skip this show
                pass

        return feeds

    def _prepare_for_batch(self, es):
        es.populate_all_episodes_list()
        for source in self.episode_metadata_sources:
            source.prepare_batch()
        for source in self.show_metadata_sources:
            source.prepare_batch()

    def get_show_id_by_name(self, name):
        name = name.lower()
        shows = self.show_source.get_show_names
        shows_lower_nospace = {self.re_remove_chars.sub("", name.lower()): show for name, show in shows.items()}
        try:
            return shows_lower_nospace[name].show_id
        except KeyError as e:
            raise NoSuchShowError from e

    def _populate_show_metadata(self, show, enable_skip_show: bool=True):
        for source in self.show_metadata_sources:
            if source.accepts(show):
                try:
                    source.populate(show)
                except SkipShow as e:
                    if enable_skip_show:
                        # Skip
                        raise e
                    else:
                        # We're not skipping this show, just go on...
                        pass

    def generate_feed_with_all_episodes(self, title=None):
        show = Show(title or SETTINGS.ALL_EPISODES_FEED_TITLE, 0)
        feed = show.init_feed()
        es = EpisodeSource(self.requests)
        self._prepare_for_batch(es)
        # Get all episodes
        episodes = [EpisodeSource.episode(self.show_source.shows[ep['program_defnr']], ep, self.requests)
                    for ep in es.all_episodes if ep['program_defnr'] != 0]
        # Populate metadata
        progress_n = len(episodes)
        for i, episode in enumerate(episodes):
            if not SETTINGS.QUIET:
                print("Populating episode {i} out of {n}".format(i=i, n=progress_n), end="\r", file=sys.stderr)
            try:
                for source in self.episode_metadata_sources:
                    if source.accepts(episode):
                        source.populate(episode)
            except SkipEpisode:
                if not SETTINGS.QUIET:
                    exc_type, exc_value, exc_traceback = sys.exc_info()
                    cause = traceback.extract_tb(exc_traceback, 2)[1][0]
                    print("NOTE: Skipping episode named {name}\n    URL: \"{url}\"\n    Caused by {cause}\n"
                          .format(name=episode.title, url=episode.sound_url, cause=cause),
                          file=sys.stderr)
                continue
            episode.add_to_feed(feed)
            episode.populate_feed_entry()

        return feed.rss_str(pretty=self.pretty_xml)
