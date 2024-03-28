saf-sync
========

This tiny Python script uses the [Termux API](https://github.com/termux/termux-api) to mirror one directory to another
using the Android Storage Access Framework (SAF).

This allows a non-root user to copy files from internal storage to external or vice versa, a la rsync. Any files/dirs present
in the destination but not the source are deleted. Any files/dirs in the source have their exact contents mirrored to the destination.

The script is very primitive and will overwrite destination files unless lengths exactly match and modification times
say the destination is at least as new, _so it is not intended for use with large files_. The Termux API can't write to
a byte range within a file, so the whole file must be overwritten.

THIS WILL NOT BE VERY FAST. Again, it's not intended for large files and will happily run you out of RAM if you try.

Setup
=====

1. Install Termux and the Termux API app. As of this writing, this script requires the latest Github builds - NOT the latest released
   version. Perhaps support for the SAF commands will be released soon.
1. Run `pkg install termux-api` within Termux (NB: in addition to installing the Termux-API APK above...)
1. Run `termux-saf-managedir` for the source directory
1. Run `termux-saf-managedir` a second time, for the destination directory
1. Run `termux-saf-dirs`. Verify both source and destination are shown. Copy their URIs.
1. Run `python saf_sync.py <SOURCE> <DESTINATION>`. Make sure to get the order of the arguments correct.
1. Profit
