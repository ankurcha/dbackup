#!/usr/bin/env python

import argparse
import sys
import math
import yaml
import hashlib
import sqlite3
import os
import os.path
import time
import shutil
import subprocess

class BackupManager:
    def __init__(self, working_dir, cronmode=False):
        self.working_dir = working_dir.decode()
        self.cronmode = cronmode
        self.db = None
        self.settings = None

    def finish(self):
        if not(self.db == None):
            self.db.close()
            del(self.db)


    def new_repository(self, watch_dir):
        # we require our working directory to be empty.
        if os.path.exists(self.working_dir):
            if len(os.listdir(self.working_dir)) > 0:
                print '''
The working directory is not empty. Cowardly refusing to create
a new working directory in a location with unexpected pre-existing
files.
'''
                sys.exit(1)

        # we need to be able to find what we're watching
        if not(os.path.exists(watch_dir)):
            print '''
The watch directory does not exist. Cannot continue.
'''
            sys.exit(1)

        # create a directory
        if not(os.path.exists(self.working_dir)):
            os.makedirs(self.working_dir)

        # create subfolders
        os.makedirs(os.path.join(self.working_dir, 'hooks'))
        os.makedirs(os.path.join(self.working_dir, 'isos'))

        # add in the default hooks
        fh = open(os.path.join(self.working_dir, 'hooks', 'process.sh'), 'w')
        fh.write('''#!/bin/sh
BASE=$1
DISC=$2
EMAIL=$3

OUT="$BASE/$DISC.log"
ERR="$BASE/$DISC.err"
ALL="$BASE/$DISC.all"

/bin/sh "$BASE/hooks/make_iso.sh" "$BASE" $DISC >"$OUT" 2>"$ERR"
RESULT=$?

echo "--------- Disc $DISC prepare log (stdout) --------" >"$ALL"
cat $BASE/$DISC.log >>"$ALL"
echo "--------- Disc $DISC prepare log (stderr) --------" >>"$ALL"
cat $BASE/$DISC.err >>"$ALL"

if [ $? -eq 0 ];
then
  mail -s "Backup disc $DISC successfully created" $EMAIL <"$ALL"
  rm "$OUT"
  rm "$ERR"
  rm "$ALL"
else
  main -s "Creation of backup disc $DISC FAILED" $EMAIL <"$ALL"
fi
''')
        fh.close()

        fh = open(os.path.join(self.working_dir, 'hooks', 'make_iso.sh'), 'w')
        fh.write('''#!/bin/sh
BASE=$1
DISC=$2

PREP_DIR="$BASE/preparing-$DISC/"
ISO="$BASE/isos/disc-$DISC.iso"

# create the ISO
echo "Creating ISO image $ISO from $PREP_DIR"
mkisofs -v -r -J -l -d --allow-multidot --allow-leading-dots --no-bak -T -o "${ISO}" "${PREP_DIR}"
if [ $? -ne 0 ];
then
  echo "An error occurred creating the ISO image"
  exit 1
fi

# augment with dvdisaster
echo "Augmenting ISO image with DVDisaster parity data..."
dvdisaster -c -mRS02 -i "${ISO}"
if [ $? -ne 0 ];
then
  echo "An error occurred augmenting the ISO with DVDisaster parity"
  exit 1
fi

# test integrity
echo "Testing parity data..."
dvdisaster -t -i "${ISO}"
if [ $? -ne 0 ];
then
  echo "The created ISO image failed DVDisaster parity test - probably disk corruption"
  exit 1
fi

# remove prep dir
rm -r "${PREP_DIR}"

# complete
echo "Completed successfully"
echo "The completed ISO file can be found at $ISO"
exit 0

''')
        fh.close()

        # create the settings yaml
        settings = {
          'watch_dir': watch_dir,
          'disc_size': 3525279744,  # 75% of a DVD+R
          'email': 'your.email@address.here'
        }
        fh = open(os.path.join(self.working_dir, 'settings.yaml'), 'w')
        yaml.dump(settings, fh, indent=4, default_flow_style=False)
        fh.close()

        # create the database
        self.db = sqlite3.connect(
          os.path.join(self.working_dir, 'manifest.db')
        )

        self.db.execute('''
            CREATE TABLE discs (
              id INTEGER PRIMARY KEY,
              started INTEGER,
              completed INTEGER,
              available BOOLEAN
            )
            ''')
    
        self.db.execute('''
            CREATE TABLE files (
              id INTEGER PRIMARY KEY,
              filename TEXT,
              timestamp INTEGER,
              md5 TEXT,
              size INTEGER,
              mtime INTEGER,
              disc_id INTEGER,
              desc TEXT,
              copied BOOLEAN
            )
            ''')

        self.db.commit()

        disc_id = self.start_disc()
        print "Staging directory created:"
        print "  Staging dir:  %s" % self.working_dir
        print "  Watched dir:  %s" % watch_dir
        print "  Current Disc: %d" % self.get_current_disc()


    def status(self):
        if not(self.settings):
            self.load_settings()

        if self.cronmode:
            pass
        else:
            print "Staging_dir:     %s" % self.working_dir
            print "Watched_dir:     %s" % self.settings['watch_dir']
            print "Emails_sent_to:  %s" % self.settings['email']
            print "Current_disc:    %d" % self.get_current_disc()
            print "Disc_threshold:  %d" % int(self.settings['disc_size'])
            (total_usage, db_usage, file_usage) = self.get_current_usage()
            print "Current_usage:   %d" % total_usage
            print "Disc_Pct_full:   %d" % int((total_usage * 100) / int(self.settings['disc_size']))
            print "Database_size:   %d" % db_usage
            print "Files_size:      %d" % file_usage
            print "Pct_database:    %d" % int((db_usage * 100) / total_usage)
            print "Pct_db_overhead: %d" % int((db_usage * 100) / int(self.settings['disc_size']))
            print "available_isos:  %d" % len(os.listdir(os.path.join(self.working_dir, 'isos')))


    def monitor(self):
        if not(self.settings):
            self.load_settings()

        real_watch = os.path.realpath(self.settings['watch_dir'])
        real_watch = real_watch.decode()

        for root, dirnames, filenames in os.walk(real_watch):
            for filename in filenames:
                fullfile = os.path.join( root, filename )
                (modified, desc) = self.is_file_changed(fullfile)
                if (modified):
                    if self.cronmode:
                        print "+ %s" % fullfile
                    else:
                        print "%s: %s" % (fullfile, desc)

                    self.add_file(fullfile, desc)


    #
    # -- Internal, Util functions ---------------------------------------------
    #
    def add_file(self, filename, change_desc='Unknown change'):
        fullfile = os.path.realpath(filename)
        real_watch = os.path.realpath(self.settings['watch_dir'])

        partfile = fullfile[len(real_watch):]
    
        # now we have the path to the file within the watch_dir,
        # we can check it against the DB
        cur = self.db.cursor()
    
        # find the current disc ID
        current_disc = self.get_current_disc()
    
        sql = "INSERT INTO files (filename, timestamp, md5, size, disc_id, desc, copied, mtime)"
        sql = sql + " VALUES (?, ?, ?, ?, ?, ?, 0, ?);"
    
        md5 = self.file_calc_md5(fullfile)
        stat = os.stat(fullfile)
        size = stat.st_size
        mtime = int(stat.st_mtime)
    
        cur.execute(sql, (partfile, time.time(), md5, size, current_disc, change_desc, mtime))
        file_id = cur.lastrowid
        self.db.commit()
    
        # now copy the file into the staging area, with the appropriate file
        # we have a max of 256 files in each directory
        # and files are numbered according to the file_id
        # so the directory numbers will be math.floor(file_id / 256)
        dir_number = int(math.floor(file_id / 256))
        path = os.path.join(self.working_dir, 'staging', 'files', '%s' % dir_number)
        dest_file = os.path.join(path, '%s' % file_id)
        if not(os.path.exists(path)):
            os.makedirs(path)
        shutil.copyfile(fullfile, dest_file)  # note, this does not preserve permissions, intentionally
    
        # now update the DB again
        cur.execute("UPDATE files SET copied=1 WHERE id=?", (file_id,))
        self.db.commit()

        # now check if the disc is full
        (total_usage, db_usage, file_usage) = self.get_current_usage()
        if (total_usage > int(self.settings['disc_size'])):
            if self.cronmode:
                print " \--- Disc %d completed --- " % current_disc
            else:
                print '*** Disc %d completed. Files: %d, DB: %d, Total: %d ***' % (current_disc, file_usage, db_usage, total_usage)

            self.close_disc(current_disc)
            new_disc = self.start_disc()

            if self.cronmode:
                print " /--- Disc %d started --- " % new_disc
            else:
                print '*** Disc %d started ***' % new_disc


    def start_disc(self):
        cur = self.db.cursor()
        os.mkdir( os.path.join( self.working_dir, 'staging' ) )
        cur.execute("INSERT INTO discs (started, completed, available) VALUES (?, NULL, 1)", (time.time(),))
        self.db.commit()
        discid = cur.lastrowid
        return discid


    def close_disc(self, disc_id):
        cur = self.db.cursor()
        cur.execute("UPDATE discs SET completed=? WHERE id=?", (time.time(), disc_id))
        self.db.commit()

        self.db.close() 
        self.db = None
    
        # copy the database file into the staging area
        shutil.copyfile(
          os.path.join(self.working_dir, 'manifest.db'),
          os.path.join(self.working_dir, 'staging', 'manifest.db')
        )
    
        self.db = sqlite3.connect(
          os.path.join(self.working_dir, 'manifest.db')
        )
    
        # move the staging area to a preparing area
        shutil.move(
          os.path.join( self.working_dir, 'staging' ),
          os.path.join( self.working_dir, 'preparing-%d' % disc_id )
        )
    
        # now spawn off the processing of the disc
        bg = subprocess.Popen(
          [ '/bin/sh', os.path.join( self.working_dir, 'hooks', 'process.sh' ), self.working_dir, "%s" % disc_id, self.settings['email'] ],
          shell=False,
          stdin=None, stdout=None, stderr=None,
          cwd=self.working_dir
        )

        if self.cronmode:
            print "  - Background processing of disc %d (PID=%d)" % (disc_id, bg.pid)
        else:
            print "*** Started background processing of disc %d (PID=%d) ***" % (disc_id, bg.pid)


    def file_calc_md5(self, filename):
        # see http://www.joelverhagen.com/blog/2011/02/md5-hash-of-file-in-python/
        fh = open(filename, 'rb')
        m = hashlib.md5()
        while True:
            data = fh.read(8192)
            if not data:
                break
            m.update(data)
        return m.hexdigest()


    def get_current_disc(self):
        cur = self.db.cursor()
    
        # find the current disc ID
        cur.execute("SELECT id FROM discs WHERE completed IS NULL ORDER BY started DESC LIMIT 1")
        rows = cur.fetchall()
    
        if len(rows) == 0:
            return None
    
        current_disc = int(rows[0][0])
        return current_disc

    def get_current_usage(self):
        current_disc = self.get_current_disc()
        cur = self.db.cursor()
        cur.execute("SELECT SUM(size) FROM files WHERE disc_id=? AND copied=1", (current_disc,))
        row = cur.fetchone()
        file_size = 0
        if not(row[0] == None):
            file_size = int(row[0])

        stat = os.stat( os.path.join( self.working_dir, 'manifest.db' ) )
        db_size = stat.st_size

        return (db_size + file_size, db_size, file_size)

    def load_settings(self):
        with open(os.path.join(self.working_dir, 'settings.yaml'), 'r') as f:
            self.settings = yaml.load(f)

        self.db = sqlite3.connect(
          os.path.join(self.working_dir, 'manifest.db')
        )

    def is_file_changed(self, filename):
        # check whether the file in question has been changed
        fullfile = os.path.realpath(filename)
        real_watch = os.path.realpath(self.settings['watch_dir'])
        partfile = fullfile[len(real_watch):]
    
        # now we have the path to the file within the watch_dir,
        # we can check it against the DB
        cur = self.db.cursor()
    
        cur.execute("SELECT md5,size,mtime FROM files WHERE filename=? AND copied=1 ORDER BY timestamp DESC LIMIT 1", (partfile,))
        rows = cur.fetchall()
    
        change = ""
        modified = False
        if len(rows) == 0:
            # it doesn't exist in the DB, so is inherently changed
            modified = True
            change = "New file"
        else:
            row = rows[0]
            db_md5 = row[0]
            db_size = int(row[1])
            db_mtime = int(row[2])
    
            stat = os.stat(fullfile)
            file_size = stat.st_size
            file_mtime = int(stat.st_mtime)
    
            if not(file_size == db_size):
                change = "%s Size changed: %d -> %d | " % (change, db_size, file_size)
                modified = True
            if not(file_mtime == db_mtime):
                change = "%s Modification time changed: %d (%s) -> %d (%s) | " % (change, db_mtime, time.ctime(db_mtime), file_mtime, time.ctime(file_mtime))
                modified = True
    
        return (modified, change.strip().strip("|").strip())

#
# ----------------------------------------------------------------------------------
#

def main():
    parser = argparse.ArgumentParser(
      description='Tool to manage incremental DVD backups with persisten indexes',
    )
    parser.add_argument(
      '-w', '--workdir',
      dest='working_dir', default=None,
      help='''The directory to use for staging files before the DVD is created. 
              This is required if the current directory is not a working dir.''',
      metavar='<working dir>'
    )
    parser.add_argument(
      '-c', '--cronmode',
      dest='cron_mode', action='store_true', default=False,
      help='Reduces verbosity to be suitable for calling from Cron'
    )
    parser.add_argument(
      'command',
      choices=['init', 'monitor', 'status', 'lost', 'usage'],
      metavar='command',
      help="One of 'init', 'monitor', 'status', 'lost' or 'usage'"
    )
    parser.add_argument(
      'detail', nargs='?', default=None, const=None,
      help="Required for 'init', 'lost' and 'help' commands. Usage is 'usage <command>'"
    )


    args = parser.parse_args()
    if args.command == 'usage':
        if args.detail == None:
            print '''
The 'usage' command gives detail on the use of the other commands.
Try one of the following:
  usage init
  usage monitor
  usage status
  usage lost
'''
            sys.exit(0)
        elif args.detail == 'init':
            print '''
Command 'init' - initialise a new working area

This command requires that the 'detail' parameter is provided. In
this mode, the 'detail' parameter specifies the location to watch
for changes.

The 'working_dir' parameter is also required in this mode.
'''
            sys.exit(0)
        elif args.detail == 'monitor':
            print '''
Command 'monitor' - check the watch directory for changes, and 
back them up

If the current working directory is a working dir, then the
'working_dir' parameter can be ommitted. If the current directory
is not a working directory, then the working_dir to use must be
specified on the command line.

This mode will iterate over all the files in the watched directory,
and add any modified files into the database.

If there is already a 'monitor' or 'lost' instance running, then 
this mode will exit with an error message.
'''
            sys.exit(0)
        elif args.detail == 'status':
            print '''
Command 'status' - reports on the current status of the backup

If the current working directory is a working dir, then the
'working_dir' parameter can be ommitted. If the current directory
is not a working directory, then the working_dir to use must be
specified on the command line.

This mode will output statistical information about the backup
set. The information is provided one field per line, in the form
<field>: <value>
'''
            sys.exit(0)
        elif args.detail == 'lost':
            print '''
Command 'lost' - mark a backup disc as no longer available

If the current working directory is a working dir, then the
'working_dir' parameter can be ommitted. If the current directory
is not a working directory, then the working_dir to use must be
specified on the command line.

This mode will set a backup disc as no longer available. If the
most recent backup of any file was on this disc, then that file
will be refreshed onto the current backup disc.

If there is already a 'monitor' or 'lost' instance running, then 
this mode will exit with an error message.
'''
            sys.exit(0)
        else:
            parser.error(
              "argument detail: invalid choice: '%s' (choose from 'init', 'monitor', 'status', 'lost')"
              % args.detail)

    if args.command == 'init':
        if args.working_dir == None:
            parser.error("The 'working_dir' parameter is required for the init command.")
        if args.detail == None:
            parser.error("The 'detail' parameter is required for the init command (it specifies the watch_dir).")
        else:
            mgr = BackupManager(args.working_dir, args.cron_mode)
            mgr.new_repository(args.detail)
            mgr.finish()
            sys.exit(0)

    # at this point, try and make an intelligent guess on the working dir
    working_dir = os.getcwd()
    if not(args.working_dir == None):
        working_dir = args.working_dir

    if not(os.path.exists(working_dir)):
        parser.error('The specified working directory does not exist.')
        sys.exit(1)

    if not(os.path.exists(os.path.join(working_dir, 'manifest.db'))):
        parser.error('The specified working directory does not contain a manifest.')
        sys.exit(1)

    if not(os.path.exists(os.path.join(working_dir, 'settings.yaml'))):
        parser.error('The specified working directory does not contain the settings file.')
        sys.exit(1)

    if not(os.path.exists(os.path.join(working_dir, 'staging'))):
        parser.error('The specified working directory does not contain a staging folder.')
        sys.exit(1)

    # create the Backup Manager object
    mgr = BackupManager(working_dir, args.cron_mode)

    if args.command == 'status':
        mgr.status()
        mgr.finish()
        sys.exit(0)

    if args.command == 'monitor':
        mgr.monitor()
        mgr.finish()
        sys.exit(0)

    if args.command == 'lost':
        pass
        mgr.finish()
        sys.exit(0)

#
# ----------------------------------------------------------------------------------
#

if __name__ == "__main__":
    main()

