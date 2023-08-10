[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

# cdzombak's fork

TODO(cdzombak): Document this fork.
TODO(cdzombak): Add launchd job example.

---

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

# Unscrobbler

This program is designed to mass-unscrobble [Last.fm](https://www.last.fm/) scrobbles based on artist, track title, or time of day of the scrobble.

For example, if you want to delete all the scrobbles by the artist Howard Shore between 11pm and 7am, that's exactly what this is for. 

## Operation

### Settings

When you run the program, you'll be prompted to enter a few values.

- Whether or not this is a trial run (if so, nothing will be deleted)
- Whether or not to delete based on time of day
    - The earliest hour to delete (will delete after this, inclusive)
    - The latest hour to delete (will delete before this, inclusive [if set to 20, will include 20:12])
    - So, everything between these two hours (that matches the rest of the criteria) will be deleted.
- Whether or not to delete based on the year
    - The year to delete (will delete with this year)
- Username
- Password
    - Your username/password are only used locally in this program. They're inputted into the Last.fm login form, and that's the only way they're shared.
- Last.fm library page number to start at (default 0)

### Output

When run, the program will generate an output file detailing each track it deletes. These files are found in `./output/`. Trial runs are denoted with `(trial)`.

### Stopping

To stop it, spam `Ctrl+C` in the terminal or close the browser window.

### Trial Runs

Instead of blindly trusting this to do what you want it to do properly, you can run it in trial mode and it won't delete anything. When you run it, just enter `Y` for Trial Mode.

Trial runs will still output results to `./output/`, so they're useful to see what it will end up deleting and maybe tweak your settings.

## Installation

### Unscrobbler.py

1. Download/install [Python 3](https://www.python.org/downloads/).

2. Download [Unscrobbler](https://github.com/TheKingElessar/Unscrobbler/releases/latest) (the `Source code (zip)`).

3. Unzip the folder. Inside the main folder (where `Unscrobbler.py` is located), open a command-line terminal. Run the following command to install dependencies: `pip3 install -r requirements.txt`.

4. Edit lines 17-18 of `Unscrobbler.py` in a text editor for your purposes. Example:

    ```
    delete_artists = ["Artist One", "Artist Two", "Also an Artist"]
    delete_songs = []
    ```
    
    ```
    delete_artists = []
    delete_songs = ["Bangarang"]
    ```

    Note that capitalization is important—if what you put in isn't perfect, it won't match what shows up on Last.fm.

5. Now, you can run Unscrobbler with the command `python Unscrobbler.py` or similar.

### Geckodriver

1. Download the relevant Geckodriver from here: https://github.com/mozilla/geckodriver/releases

2. Unzip the downloaded file and place the contained `.exe` file in the same directory as `Unscrobbler.py`.
