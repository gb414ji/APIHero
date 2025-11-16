# APIHero - Burp Suite Extension for CSV Endpoint Export

<img width="1024" height="1024" alt="Gemini_Generated_Image_h71tm4h71tm4h71t" src="https://github.com/user-attachments/assets/e2e18b3d-6aa7-4b5e-b176-63c8b233efc3" />


**APIHero** is a lightweight Burp Suite extension for extracting and exporting API endpoints from your site's sitemap. It focuses on simplicity, usability, and CSV export. Numeric or UUID path segments are automatically replaced with `{id}` placeholders for better reusability.

---

## Features

- Browse your site's sitemap with a **tree view**.
- Preview endpoints **grouped by host → top-level folder**.
- Automatic `{id}` placeholders for numeric/UUID path segments.
- Export endpoints to a **CSV file** with structured columns:
  - Host
  - Top-Level Folder
  - HTTP Method
  - Endpoint URL
- Fully compatible with **Jython 2.7** for Burp Suite.
- Minimalist, lightweight UI for fast performance.

---

## Screenshots

*(Optional: Add screenshots of the Burp Suite tab here)*

---

## Installation

1. Download the latest `apihero.py` from this repository.
2. Open **Burp Suite → Extender → Extensions → Add**.
3. Select:
   - Extension Type: **Python**
   - Extension File: `API_HERO_V1.0.py`
4. Ensure **Jython 2.7** standalone JAR is configured in Burp.
5. The extension will appear as a new tab labeled **APIHero**.

---

## Usage

1. Navigate the **Site Map** tree in APIHero.
2. **CTRL+Click** to select multiple hosts or folders.
3. Click **Load Selected** to preview endpoints in the right panel:
   - Hosts and top-level folders are shown
   - Endpoint count per folder displayed
   - `{id}` placeholders automatically applied
4. Click **Export CSV** to save all endpoints to a CSV file:
   - CSV columns: Host, Top-Level Folder, Method, Endpoint
   - Maintains the same hierarchy/order as preview

---

## CSV Output Example

```csv
Host,Top-Level Folder,Method,Endpoint
example.com,users,GET,/users/{id}/profile
example.com,posts,POST,/posts/{id}/comment
