# 🚀 CVE-2026-41940 – cPanel & WHM / WP Squared Auth Bypass Exploitation Tool

[![Python 3.8+](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![CVE-2026-41940](https://img.shields.io/badge/CVE-2026--41940-critical-red)](https://nvd.nist.gov/vuln/detail/CVE-2026-41940)

A comprehensive Python utility to **detect**, **scan in bulk**, and **exploit** the critical authentication bypass vulnerability (CVE-2026-41940) in cPanel & WHM and WP Squared.  
The tool combines multi‑port smart scanning, multi‑threading, Google dork generation, interactive remote command execution (RCE), and structured report export.

> ⚠️ **WARNING** – This tool is intended **only** for authorised security testing and educational purposes.  
> Unauthorised use against systems you do not own or have explicit permission to test is **illegal**.  
> The author assumes **no liability** for any misuse or damage.

---

## 📌 About CVE-2026-41940

| Detail | Value |
|--------|-------|
| **CVE ID** | CVE-2026-41940 |
| **Severity** | Critical (CVSS 9.8) |
| **Affected Software** | cPanel & WHM ≥ 11.40 (all unpatched versions) + WP Squared |
| **Impact** | Complete authentication bypass → full WHM administrative access |
| **Remote Code Execution** | Yes, via WHM API after bypass |
| **Published** | 2026-04-28 |
| **Exploitation in the wild** | Active since day zero; public PoC available |
| **Official Advisory** | [cPanel Support](https://support.cpanel.net/hc/en-us/articles/40073787579671) |

The vulnerability allows an unauthenticated attacker to send a specially crafted `Authorization` header to completely bypass the login flow, gaining root‑level control of the server.

---

## ✨ Features

- **CVE description** – built‑in technical summary.
- **Google dork generator** – ready‑to‑use search queries for finding exposed cPanel/WHM instances.
- **Smart multi‑port scanning** – accepts a bare IP/hostname and automatically probes all six common cPanel/WHM/Webmail ports.
- **Fast** – multi‑threaded scanning (configurable).
- **Single‑target or bulk file input** – scan one URL or load a list from a text file.
- **Full remote code execution (RCE)** – interactive shell on vulnerable WHM ports, with fallback web‑shell protection.
- **Safety guard** – exploitation only allowed on WHM ports (2086/2087); detection works on all ports.
- **Report export** – save results as JSON or HTML, with automatic timestamps.

---

## ⚙️ Installation

```bash
# Clone the repository
git clone https://github.com/NULL200OK/cve-2026-41940-tool.git
cd cve-2026-41940-tool

```
# 🔧 Usage
Run the script:

```bash
python cve_2026_41940_tool.py
```
**You will be greeted with an interactive menu:**
```bash
text
1. Google dorks
2. Scan target(s)
3. Exploit (RCE)
```
# 🎯 Target format & port handling

**cPanel/WHM services run on specific non‑standard ports:**

**Service**	|**HTTP**	|**HTTPS**

  **WHM**	  |2086	|2087

**cPanel**	|2082	|2083

**Webmail**	|2095	|2096

**How to provide a target:**

192.168.1.5 – automatically scans all six common ports (2082-2087, 2095-2096).

192.168.1.5:2087 – scans only WHM HTTPS.

https://server.com:2087 – uses exactly that URL (scheme must be included).

**Important:**

Detection works on any of the above ports.

Exploitation (RCE) is restricted to WHM ports (2086/2087) only, because the WHM API is required.

For batch scanning, create a plain text file with one target per line (same format as above). The tool will expand each line accordingly.

## 1️⃣ Google Dorks
Prints a list of search queries to discover cPanel/WHM login pages.

You can save the dorks as a JSON or HTML file.

# 2️⃣ Scan Target(s)

Choose single target or a file with many targets.

The scanner checks the vulnerability by sending the bypass header to appropriate API endpoints.

Results are displayed in real time, with clear [+] / [-] indicators.

After scanning, you can save the results to a structured report.

# 3️⃣ Exploit (RCE)

Only works on WHM ports (2086/2087) – the tool will refuse otherwise.

It first verifies the target is indeed vulnerable.

If vulnerable, an interactive shell is spawned – type any command (e.g., id, uname -a, cat /etc/passwd) and get the output.

**Two methods are used, with automatic fallback:**

Direct WHM API command execution.

Upload of a temporary PHP web shell (deleted immediately after the command).

Type exit to leave the shell.

# 🧠 Detection Logic

The tool sends a crafted Authorization header (base64 of cpanel:forbidden) to API endpoints like /json-api/listaccts or /json-api/version.
On a vulnerable server, this bypasses authentication and returns sensitive data or a 200 response without redirecting to the login page.
On a patched system, a 401 (Unauthorized), 403 (Forbidden), or a redirect to the login page is expected.

# 🤝 Contributing

Pull requests, issues, and feature suggestions are welcome. For major changes, please open an issue first to discuss your ideas.

# 📄 License

This project is licensed under the MIT License – see the LICENSE file for details.

# ❤️ Disclaimer
This tool is provided for educational and authorised security research only.
The user assumes all responsibility for compliance with applicable laws.
**Use it wisely**
