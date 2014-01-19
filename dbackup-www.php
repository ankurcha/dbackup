<?php

# Our config file is stored alongside the script (from the
# web server's perspective)
# __FILE__ resolves symlinks, so this can exist outside of
# the web server's visibility, if the entry in wwwroot is
# a symlink to this script somewhere.
$cfg_file = dirname(__FILE__) . '/dbackup-web.cfg';

if (!file_exists($cfg_file)) {
  show_error("The configuration file does not exist.");
  exit();
}

# read the config file
# The config file is in the form:
# <key>: <path>: <disc size>
# Each entry should be on its own line
# Whitespace from the key and path will be stripped
# Comment lines start with "!" "#" or ";"
# Lines that do not conform to <key>:<path>:<disc size> will be skipped
$cfg = array();
$fh = fopen($cfg_file, 'r');
while (!feof($fh)) {
  $line = fgets($fh);
  $first_char = substr($line, 0, 1);
  if ($first_char != ';' and
      $first_char != '#' and
      $first_char != '!') {
    $parts = explode(":", $line);
    if (sizeof($parts) == 3) {
      $key = trim($parts[0]);
      $path = trim($parts[1]);
      $cfg[$key] = array();
      $cfg[$key]['path'] = $path;
      $cfg[$key]['size'] = trim($parts[2]);
    }
  }
}
fclose($fh);

$mode = "index";
if (isset($_GET['view'])) {
  $mode = $_GET['view'];
}

switch ($mode) {
  case 'index':
  default:
    show_index();
}


function show_index() {
  global $cfg;
  html_start("DBackup Summary");
  ?>
  <h1>DBackup Web Interface - Index</h1>
  <div id="breadcrumb">
    <a href="#">Index</a>
  </div>
  <table>
    <tr>
      <th>Backup Set</th>
      <th>Number of files</th>
      <th>Latest addition</th>
      <th>Completed Discs</th>
      <th>Current disc progress</th>
    </tr>
    <?
    $keys = array_keys($cfg);
    sort($keys);
    foreach($keys as $key) {
      $summary = db_summary($key);
      ?>
      <tr>
        <td><a href="#"><?=$key?></a></td>
        <td><?=$summary['file_count']?></td>
        <td><?=date('D d M Y, H:i:s', $summary['latest'])?></td>
        <td><?=$summary['completed_discs']?></td>
        <td>
          <div class="mini"><?=$summary['current_total_size']?> / <?=$summary['current_max_size']?></div>
          <div>
            <?=round($summary['current_progress'])?>%:
            <span class="progress-bar">
              <span style="width: <?=round($summary['current_progress'])?>%"></span>
            </span>
          </div>
        </td>
      </tr>
      <?php
    }
    ?>
  </table>
  <?php
  html_end();
}

function show_error($msg) {

}

function html_start($title) {
  ?>
<html>
  <head>
    <title><?=$title?></title>
    <style>
/* See http://colorschemedesigner.com/#3x41Tw0w0w0w0 */
html,body {
  background-color: #25567B;
  color: white;
  margin: 0;
  border: 0;
  padding: 0;
  font-family: sans-serif;
}
a:link {
  color: #7373D9;
  text-decoration: none;
}
a:hover {
  text-decoration: underline;
}
a:visited {
  color: #7373D9;
  text-decoration: none;
}
a:active {
  color: #7373D9;
  text-decoration: none;
  font-weight: bold;
}
h1,h2,h3,h4 {
  text-align: center;
}
#content {
  width: 800px;
  margin: 0 auto;
  background-color: #033E6B;
  min-height: 100%;
}
#breadcrumb {
  width: 100%;
  padding-top: 0.2em;
  padding-bottom: 0.2em;
  padding-left: 0.5em;
  border-top: 1px solid #25567B;
  border-bottom: 1px solid #25567B;
  margin-bottom: 0.7em;
}
table {
  width: 90%;
  margin-left: 5%;
  border-collapse: collapse;
}
td {
  border-left: 1px solid #3F92D2;
  border-right: 1px solid #3F92D2;
  border-bottom: 1px solid #3F92D2;
  padding: 0;
  margin: 0;
  text-align: center;
}
th {
  border-left: 1px solid #033E6B;
  border-right: 1px solid #033E6B;
  background-color: #3F92D2;
  padding: 0;
  margin: 0;
}
span.progress-bar {
  display: inline-block;
  width: 100px;
  height: 10px;
  border: 1px solid #FFC373;
  text-align: left;
}
span.progress-bar span {
  display: inline-block;
  background-color: #FFAD40;
  height: 100%;
}
.mini {
  font-size: 0.7em;
}
    </style>
  </head>
  <body>
    <div id="content">
  <?php
}

function html_end() {
  ?>
    </div>
  </body>
</html>
  <?php
}

function db_summary($id) {
  global $cfg;

  if (!array_key_exists($id, $cfg)) {
    return;
  }

  // open the db
  $db = new SQLite3($cfg[$id]['path'] . '/manifest.db', SQLITE3_OPEN_READONLY);
  $ret = array();
  $ret['file_count'] = $db->querySingle("SELECT COUNT(DISTINCT filename) FROM files");
  $ret['latest'] = $db->querySingle("SELECT timestamp FROM files ORDER BY timestamp DESC LIMIT 1");
  $ret['current_disc'] = $db->querySingle("SELECT id FROM discs WHERE completed IS NULL ORDER BY id DESC LIMIT 1");
  $ret['completed_discs'] = $db->querySingle("SELECT id FROM discs WHERE completed IS NOT NULL ORDER BY id DESC LIMIT 1");
  $ret['current_files_size']= $db->querySingle("SELECT SUM(size) FROM files WHERE disc_id=". $ret['current_disc']);

  $s = stat($cfg[$id]['path'] . '/manifest.db');
  $ret['current_db_size'] = $s['size'];

  $ret['current_total_size'] = $ret['current_files_size'] + $ret['current_db_size'];
  $ret['current_max_size'] = $cfg[$id]['size'];
  $ret['current_progress'] = ($ret['current_total_size'] * 100) / $ret['current_max_size'];

  $db->close();
  return $ret;
}

?>
