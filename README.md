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


## Detail

dBackup works by watching a directory for files that have changed (determined
by checking their filesize and the modification time on the file). If it
determines a file has changed, that file is copied into a working directory,
and recorded in a database.

When the working directory exceeds a threshold size, a script is run to
generate a DVD ISO, and a new disc is started. Each ISO image contains a
snapshot of the database at time of creation, and so contains a copy of the
backup history to that point.

The database is a SQLite3 database, with 2 tables:

- "discs" contains information about the discs in the set. It has 4 columns:
  - "id" is the primary key for the table. This identifies the disc
  - "started" is the Unix epoch timestamp that the disc was started
  - "completed" is the Unix epoch timestamp that the disc was closed. This is
    NULL for the currently opened disc
  - "available" is a 1/0 flag indicating whether this disc is available, or
    has been lost.

- "files" contains information about individual files within the set.
  - "id" is the primary key for the table. It uniquely identifies each backed
    up file. It maps to the filename used for the associated file within it
    backup disc.
  - "filename" is the original filename (including path, relative to the watched
    directory) for the associated file.
  - "timestamp" is the Unix epoch timestamp that the backup was taken.
  - "md5" is the MD5 checksum of the file, and can be used to verify its
    integrity within the watched directory, or on a backup disc.
  - "size" is the size in bytes for the file.
  - "mtime" is the Unix epoch modification time of the backed up file. This is
    used in associated with "size" to determine if a file has changed.
  - "disc\_id" is the reference to the primary key in the "discs" table, for the
    disc which contains this backed up file.
  - "desc" is a text description for the reason that this backup was made
  - "copied" is an internal flag indicating whether the file has been copied
    into the disc, or whether the ID has merely been reserved for the file, ahead
    of the copying completing.


## Disclaimer

dBackup is not meant to replace reliable storage, or to provide an alternative
to a strong multi-versioned backup strategy. If your data is that critical to
you, then you should invest accordingly.

dBackup IS designed to help automate good "simple" backup practise by automatically
detecting when a file has changed, taking a copy of it, constructing DVD ISO
images of the copies, and giving you the tools to locate the copies within the
generated images.

dBackup makes no guarantees to preventing data loss, or to being able to recover
your data in the event of a failure. You are encouraged to read the source code,
and to make sure you understand how the SQLite database is structured, so that:

1. You can be confident that you understand how dBackup archives your data, and
   that it doesn't leave anything out,

2. That you have the understanding to locate an appropriate copy of your data
   from only the burned DVDs, and the SQLite databases within (e.g. data recovery
   without relying on the dBackup tools)


## Warning!

Because it is designed for data that is incrementally built up over time (such
as photos or music), there is a risk of not being able to recover old, deleted
data in the event that a backup disc is lost.

It sounds obvious, but because dBackup maintains a single backup of a version of
a file, and that it only takes a snapshot whenever it detects a file has changed,
then if the DVD containing a particular version of a file is lost, the only place
that it can be recovered from is the origin directory.

In the event that the file has been deleted, and the "lost" DVD was
the disc that contained the most recent version of the file, then there is no
way of recovering that data.

This is especially pertinent when you consider that moving a file is effectively
creating a copy of it, and deleting the original. dBackup will see a new file,
and track it, but the original file will be apparently deleted, and could be
reported as lost data.

As a rule of thumb, if you only ever add data to a directory, then any "lost
data" reported as a result of processing a lost disc should relate to a renamed
file.


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
