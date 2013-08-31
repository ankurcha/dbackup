# dBackup: Simple Incremental Folder Backup

## Overview

dBackup is a small and simple Python script to handle incremental backups
of a folder. It is mainly designed to be run periodically (e.g. from cron),
and will detect any changes to files in the watched directory, and will stage
them for future writing to CD/DVD.

Each generated disc contains a full history of the backup set up to that
point.

dBackup is well suited to collections of data which are incremental, and where
files change infrequently. It was originally written to provide a structured
automatic backup for collections of Photos and Music.

If you are looking for a backup methodology for frequently changed data,
dBackup may not be well suited. Whilst dBackup stores each changed file intact,
frequently changing data may be better archived using a system that stores
deltas.

## Example Usage

Create new repository:
```
> dbackup.py -w /tmp/staging-dir init /tmp/watched-dir
Staging directory created:
  Staging dir:  /tmp/staging-dir
  Watched dir:  /tmp/watched-dir
  Current Disc: 1
```

Check status of repository:
```
> dbackup.py -w /tmp/staging-dir status
Staging_dir:     /tmp/staging-dir
Watched_dir:     /tmp/watched-dir
Emails_sent_to:  your.email@address.here
Current_disc:    1
Disc_threshold:  3525279744
Current_usage:   3072
Disc_Pct_full:   0
Database_size:   3072
Files_size:      0
Pct_database:    100
Pct_db_overhead: 0
available_isos:  0
```

Stage any changes:
```
> dbackup.py -w /tmp/staging-dir monitor
/tmp/watched-dir/foo1: New file
/tmp/watched-dir/foo2: New file
/tmp/watched-dir/foo3: New file
```

Disc images are structed with the files in a numeric directory structure, and
a SQLite manifest file located in the root of the disc.

The manifest database includes references to previously generated discs -
basically a complete history, allowing files to easily be receovered if
required.
