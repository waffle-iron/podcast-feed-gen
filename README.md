# Podcast feed generator for Radio Revolt #

Generate podcast feeds that can act as drop-in replacement for the existing podcast feeds, and work well with podcast apps.

The main goal is to **eliminate the need for Feedburner**, since Google might shut it down whenever they feel like it.


## Features ##

* **Use metadata** like episode title, description, image and link from dusken.no/radio and radiorevolt.no (using podcast date to decide which of them to use)
* Use metadata like feed title, description and image from dusken.no/radio or radiorevolt.no (whichever is in use)
* Only publish a podcast episode if its corresponding episode post on dusken.no/radio or radiorevolt.no is published (enabling **preproduction of podcasts**)
* Follow the **guidelines set by iTunes** so that the feed can be used directly by it.
* **Preserve** existing episodes the way they are.


## Technologies ##

This project uses Python v3.4 only, and is written so that the podcast feeds can be updated regularly (by something like
 a cron job) or generated afresh each time a feed is accessed (potentially with a cache).


## How to set up ##

1. [Use virtualenv!](https://iamzed.com/2009/05/07/a-primer-on-virtualenv/)

   ```bash
   virtualenv -p python3.4 venv
   . venv/bin/activate
   ```

2. Install the following packages (assuming Ubuntu/Debian):

    * libxml2
    * libxml2-dev
    * libxslt1.1
    * libxslt1-dev
    * python3-lxml

3. Install build dependencies for python and its lxml-bindings by running `sudo apt-get build-dep python3-lxml` (still assuming Ubuntu/Debian)

4. Install dependencies by running one of the two commands below. You must decide if you want to run a Python web server for serving freshly generated podcast feeds, or generate podcast feeds periodically and serve the generated feeds with some other HTTP server.
    <dl>
        <dt>Run web-server and generate feeds on-the-fly</dt>
        <dd><code>pip install -r webserver/requirements.txt</code></dd>
        <dt>Generate feeds periodically</dt>
        <dd><code>pip install -r generator/requirements.txt</code></dd>
    </dl>

5. Copy `generator/settings_template.py` to `generator/settings.py` and fill in settings.
6. Do the same with `webserver/settings_template.py` if you intend to use the provided web server.


## Scripts ##

<dl>
    <dt>generate_feed.py</dt>
    <dd>Generate RSS feed for a single podcast.</dd>
    <dt>batch_generate_feed.py</dt>
    <dd>Generate RSS feeds for all known podcasts.</dd>
    <dt>server.py</dt>
    <dd>Run web server which generates podcast feeds as they're requested.</dd>
    <dt>utils/mod_rewrite.py</dt>
    <dd>Generate configuration for Apache mod_rewrite, which can be used to redirect to the generated feeds (useful when
    running <code>batch_generate_feed.py</code> as a background task and serving the generated RSS files using Apache,
     not <code>server.py</code>)</dd>
</dl>

Use the `--help` flag to see available options for any script.


## Configuration ##

<dl>
    <dt>generator/settings.py</dt>
    <dd>Settings for feed generation.</dd>
    <dt>webserver/settings.py</dt>
    <dd>Settings for the web server.</dd>
</dl>


## Details: How it works ##

### Generating the feed for a podcast ###

First, the show is matched with one of the shows in `show_source`. It will fetch basic information about the show,
like the show name. In the case of generating the feed for one single podcast, the `show_source` doesn't do much –
its primary purpose is to iterate through all shows.

Next, metadata for the show is fetched by all registered `metadata_sources.show` classes. This is done by querying each
metadata source for whether it has metadata for this show or not. If it has, it is asked to populate the show with new
metadata. The order in which the metadata sources are asked, is defined in `generator/metadata_sources/__init__.py`.
Later sources override information from the earlier ones.

Now, episodes for this podcast are fetched. The `episode_source` is responsible for this.
It also writes basic metadata for all episodes.

Secondly, registered `metadata_sources/episode` classes may act on a subset of the episodes and add or overwrite the existing metadata with
new data, much like the `metadata_sources/show`. Furthermore, each metadata source has a method for figuring out if this
is a relevant episode for this source. If it is, then the metadata source is asked to edit the Episode object.

Both in the case of shows and episodes, multiple metadata sources may act on a single show/episode. This way, one
metadata source may provide only the link to the podcast image, while another source provides the textual description.
Still, if multiple sources provide the same attribute, later metadata sources will override metadata from earlier sources. The order in which the metadata sources appear
in `generator/metadata_sources/__init__.py` is thus of big importance.

Note that it is perfectly acceptable for no metadata source to match an episode or show – in such cases, the default
metadata from the `episode_source` or `show_source` is used, respectively.
