import cgi
import getopt
import http.server
import pathlib
import os
import sqlite3
import sys
import time
import urllib.parse

DB_FILENAME = 'build_utils.db'

def get_next_build_num(params):
    product_name = urllib.parse.unquote(params.get('product') or '')
    version_str = urllib.parse.unquote(params.get('version') or '')
    commit = urllib.parse.unquote(params.get('commit') or '')
    if not product_name:
        return {'error': 'next_build_num command missing required parameter "product"'}
    if not version_str:
        return {'error': 'next_build_num command missing required parameter "version"'}
    if not commit:
        return {'error': 'next_build_num command missing required parameter "commit"'}

    conn = sqlite3.connect(DB_FILENAME)
    cur = conn.cursor()

    # get or insert the product
    cur.execute('select id from product where name = ?', (product_name,))
    row = cur.fetchone()
    if row:
        prod_id = row[0]
    else:
        cur.execute('insert into product(name) values (?)', (product_name,))
        prod_id = cur.lastrowid

    # get or insert the version
    cur.execute(
        'select id from version where product_id = ? and version_str = ?',
        (prod_id, version_str))
    row = cur.fetchone()
    if row:
        version_id = row[0]
    else:
        cur.execute(
            'insert into version(product_id, version_str) values (?, ?)',
            (prod_id, version_str))
        version_id = cur.lastrowid

    # get the next higher build number to insert
    build_num = 1
    cur.execute(
        'select max(build_num) from build where version_id = ? group by version_id',
        (version_id,))
    row = cur.fetchone()
    if row:
        build_num = row[0] + 1

    timestamp = time.time()
    cur.execute(
        'insert into build(version_id, build_num, timestamp, commit_id) '
        'values (?, ?, ?, ?)',
        (version_id, build_num, timestamp, commit))

    conn.commit()
    conn.close()

    return {
        'next_build_num': build_num,
        'timestamp': timestamp,
    }

def get_data_for_version(product_name, version_str):
    conn = sqlite3.connect(DB_FILENAME)
    cur = conn.cursor()

    cur.execute(
        'select version.id  '
        'from product, version '
        'where product.id = version.product_id and '
        '  product.name = ? and version.version_str = ?',
        (product_name, version_str))

    row = cur.fetchone()
    if not row:
        return []

    version_id = row[0]

    cur.execute(
        'select build_num, timestamp, commit_id  from build '
        'where version_id = ? order by build_num desc', (version_id,))

    results = cur.fetchall()

    conn.close()
    return results

class BuildHandler(http.server.BaseHTTPRequestHandler):
    def write_wfile(self, s):
        self.wfile.write(s.encode("utf-8"))

    def send_text_headers(self):
        self.send_response(200)
        self.send_header('Content-type','text/plain')
        self.end_headers()

    def send_html_headers(self):
        self.send_response(200)
        self.send_header('Content-type','text/html')
        self.end_headers()

    def parse_path(self):
        params = {}
        path_parts = self.path.split('?')
        cmd = path_parts[0]
        if len(path_parts) > 1:
            param_strs = path_parts[1].split('&')
            for param_str in param_strs:
                param_parts = param_str.split('=')
                if len(param_parts) == 2:
                    params[param_parts[0]] = param_parts[1]
        return (cmd, params)

    def handle_get_next_build_num(self, params):
        self.send_text_headers()
        ret_vals = get_next_build_num(params)
        self.write_wfile(str(ret_vals))

    def write_results_for_build_version(
        self, version_data, product_name, version_str):

        if len(version_data) == 0:
            self.write_wfile('No data found for {0} {1}\n'.
                format(product_name, version_str))
            return

        self.write_wfile('Build data for {0} {0}:<br /><br />'.
            format(product_name, version_str))

        self.write_wfile(
"""
<table>
  <tr>
    <th>Build</th>
    <th>Timestamp</th>
    <th>Commit</th>
  </tr>
""")

        for (build_num, timestamp, commit) in version_data:
            timestamp = time.gmtime(timestamp)
            timestamp_str = time.strftime("%a, %d %b %Y %H:%M:%S", timestamp)
            self.write_wfile(
"""
    <tr>
        <td>{0}</td>
        <td>{1}</td>
        <td>{2}</td>
    </tr>
""".format(build_num, timestamp_str, commit))

        self.write_wfile(
"""
</table>
""")

    def handle_get_build_data(self, params):
        product_name = urllib.parse.unquote(params.get('product') or '')
        version_str = urllib.parse.unquote(params.get('version') or '')

        self.send_html_headers()
        self.write_wfile(
"""
<html>
<head>
    <style>
        th, td {{
            border: 1px solid black;
        }}
    </style>
</head>
<body>

<iframe name="form_dest" style="display: none;"
 onload="if (did_submit) {{window.location.reload()}}"></iframe>
<form method="post" action="/cmd/next_build_num" target="form_dest"
  onsubmit="did_submit = true;">
  <input type="hidden" name="product" value="{0}">
  <input type="hidden" name="version" value="{1}">
  Commit ID: <input type="text" name="commit">
  <button type="submit">
    Generate next build number
  </button>
</form>

""".format(product_name, version_str))

        if not product_name:
            self.write_wfile('bad request: need a valid product name')
        elif not version_str:
            self.write_wfile('bad request: need a valid version')
        else:
            version_data = get_data_for_version(product_name, version_str)
            self.write_results_for_build_version(
                version_data, product_name, version_str)

        self.write_wfile('</body>\n</html>\n')

    def do_GET(self):
        (cmd, params) = self.parse_path()

        if cmd == '/cmd/get_build_data':
            self.handle_get_build_data(params)
        else:
            self.send_error(404, "Invalid path")

    def do_POST(self):
        (cmd, params) = self.parse_path()

        if not len(params):
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={"REQUEST_METHOD": "POST"}
            )

            params = {}
            for item in form.list:
                params[item.name] = item.value

        if cmd == '/cmd/next_build_num':
            print('do /cmd/next_build_num')
            self.handle_get_next_build_num(params)
        else:
            self.send_error(404, "Invalid path")

def ensure_db_exists():
    db_file = pathlib.Path(DB_FILENAME)
    if db_file.is_file():
        return

    script_file = open('db_scripts.sql')
    scripts = script_file.read()

    conn = sqlite3.connect(DB_FILENAME)
    conn.executescript(scripts)
    conn.close()

def run(port, server_class=http.server.HTTPServer, handler_class=BuildHandler):
    ensure_db_exists()
    server_address = ('', port)
    httpd = server_class(server_address, handler_class)
    httpd.serve_forever()

def print_usage():
    print('usage: python build_utils_server.py [-p] <port>')

def main():
    port = 9000
    try:
        parsed_args = getopt.getopt(sys.argv[1:], 'p:')
    except getopt.GetoptError as e:
        print('error: ' + e.msg)
        print_usage()
        sys.exit(1)

    for opt, optarg in parsed_args[0]:
        if opt == '-p':
            try:
                port = int(optarg)
                if port <= 0:
                    raise ValueError()
            except ValueError as e:
                print('error: illegal value for option "-p": must be a positive number')
                sys.exit(1)

    run(port)

main()
