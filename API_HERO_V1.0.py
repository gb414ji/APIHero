# -*- coding: ascii -*-
# apihero.py - APIHero CSV Export Only (Jython 2.7 compatible)

from burp import IBurpExtender, ITab
from javax.swing import JPanel, JScrollPane, JSplitPane, JButton, JTextArea, JFileChooser, JOptionPane
from javax.swing import JTree
from javax.swing.tree import DefaultMutableTreeNode, DefaultTreeModel, TreeSelectionModel
from java.awt import BorderLayout, Dimension
from java.lang import Thread, Runnable
from java.io import File
import os, re, traceback

# -------------------------
# Helpers / Config
# -------------------------
ID_RE = re.compile("(^|/)([0-9a-fA-F]{8,}|[0-9]+)(?=$|/)")

def normalize_path_for_placeholders(url):
    """Replace numeric/UUID path segments with {id}."""
    if url is None:
        return ""
    try:
        s = str(url)
    except:
        s = url
    if "://" in s:
        parts = s.split("/", 3)
        path = "/" + parts[3] if len(parts) >= 4 else "/"
    else:
        path = s
    path = path.split("?", 1)[0]
    path = ID_RE.sub(lambda m: m.group(1) + "{id}", path)
    path = re.sub("/+", "/", path)
    if path.endswith("/") and len(path) > 1:
        path = path[:-1]
    return path

# -------------------------
# File chooser
# -------------------------
def choose_file(default_name):
    """Open JFileChooser or fallback to home directory."""
    try:
        fc = JFileChooser()
        fc.setSelectedFile(File(default_name))
        result = fc.showSaveDialog(None)
        if result == JFileChooser.APPROVE_OPTION:
            return fc.getSelectedFile().getAbsolutePath()
    except:
        pass
    home = os.path.expanduser("~")
    return os.path.join(home, default_name)

# -------------------------
# Tree builder Runnable
# -------------------------
class TreeBuilder(Runnable):
    def __init__(self, ext):
        self.ext = ext
    def run(self):
        try:
            self.ext._build_tree_from_sitemap()
        except:
            try:
                self.ext._err("TreeBuilder exception:\n" + traceback.format_exc())
            except:
                pass

# -------------------------
# Main BurpExtender Class
# -------------------------
class BurpExtender(IBurpExtender, ITab):

    def registerExtenderCallbacks(self, callbacks):
        # ---------------- Init ----------------
        self._callbacks = callbacks
        self._helpers = callbacks.getHelpers()
        self._callbacks.setExtensionName("apihero")
        try:
            self.stdout = callbacks.getStdout()
            self.stderr = callbacks.getStderr()
        except:
            self.stdout = None
            self.stderr = None
        self.node_map = {}
        self.tree_model = None

        # ---------------- UI ----------------
        self._build_ui()
        callbacks.addSuiteTab(self)
        Thread(TreeBuilder(self)).start()
        self._log("apihero loaded. Site map indexing running in background.")

    # ---------------- ITab ----------------
    def getTabCaption(self):
        return "APIHero"
    def getUiComponent(self):
        return self.panel

    # ---------------- Logging ----------------
    def _log(self, s):
        try:
            if self.stdout:
                self.stdout.write(s + "\n"); self.stdout.flush()
            else:
                print(s)
        except:
            pass
    def _err(self, s):
        try:
            if self.stderr:
                self.stderr.write(s + "\n"); self.stderr.flush()
            else:
                print("ERR: " + s)
        except:
            pass

    # ---------------- UI Build ----------------
    def _build_ui(self):
        root = DefaultMutableTreeNode("Site Map (loading...)")
        self.tree_model = DefaultTreeModel(root)
        self.tree = JTree(self.tree_model)
        self.tree.getSelectionModel().setSelectionMode(TreeSelectionModel.DISCONTIGUOUS_TREE_SELECTION)
        self.tree.setRootVisible(True)
        self.tree.setShowsRootHandles(True)

        self.panel = JPanel(BorderLayout())
        top = JPanel()
        self.btnLoad = JButton("Load Selected", actionPerformed=self._on_load_selected)
        self.btnCSV = JButton("Export CSV", actionPerformed=self._on_export_csv)
        self.btnHelp = JButton("Help", actionPerformed=self._on_help)
        top.add(self.btnLoad); top.add(self.btnCSV); top.add(self.btnHelp)

        self.preview = JTextArea()
        self.preview.setEditable(False)
        self.preview.setPreferredSize(Dimension(500,400))

        split = JSplitPane(JSplitPane.HORIZONTAL_SPLIT, JScrollPane(self.tree), JScrollPane(self.preview))
        split.setDividerLocation(350)

        self.panel.add(top, BorderLayout.NORTH)
        self.panel.add(split, BorderLayout.CENTER)

    # ---------------- Tree / Node Helpers ----------------
    def _ensure_expanded(self):
        try:
            for i in range(self.tree.getRowCount()):
                try: self.tree.expandRow(i)
                except: pass
        except: pass

    def _node_full_prefix(self, node):
        parts = []
        curr=node
        while curr is not None:
            parts.insert(0,str(curr.getUserObject()))
            curr = curr.getParent()
        if parts and parts[0].lower().startswith("site map"): parts=parts[1:]
        if not parts: return ""
        if len(parts)==1: return parts[0]
        return parts[0]+"/"+"/".join(parts[1:])

    def _collect_entries_for_selected(self):
        self._ensure_expanded()
        sel = self.tree.getSelectionPaths()
        if not sel: return []
        collected = []; seen=set()
        for p in sel:
            node = p.getLastPathComponent()
            prefix = self._node_full_prefix(node)
            if not prefix: continue
            for key,lst in self.node_map.items():
                if key.startswith(prefix):
                    for e in lst:
                        if e not in seen:
                            seen.add(e)
                            collected.append(e)
        return collected

    # ---------------- Tree Build ----------------
    def _build_tree_from_sitemap(self):
        try:
            entries = self._callbacks.getSiteMap(None)
        except Exception as e:
            self._err("getSiteMap failed: " + str(e))
            entries = []

        hosts = {}
        for e in entries:
            try:
                analyzed = self._helpers.analyzeRequest(e)
                url = str(analyzed.getUrl())
            except:
                try: url = e.getUrl().toString()
                except: continue
            parts = url.split("/",3)
            if len(parts) < 3: continue
            host = parts[0] + "//" + parts[2]
            path = "/" + parts[3] if len(parts) >=4 else "/"
            hosts.setdefault(host, []).append((path,e))

        root = DefaultMutableTreeNode("Site Map")
        model = DefaultTreeModel(root)
        node_map = {}
        for host, items in sorted(hosts.items()):
            host_node = DefaultMutableTreeNode(host)
            model.insertNodeInto(host_node, root, root.getChildCount())
            for path, entry in sorted(items):
                segs = [s for s in path.split("/") if s]
                parent = host_node
                accum = host
                for seg in segs:
                    accum = accum + "/" + seg
                    found = None
                    for i in range(parent.getChildCount()):
                        c = parent.getChildAt(i)
                        if str(c.getUserObject()) == seg:
                            found = c
                            break
                    if found is None:
                        child = DefaultMutableTreeNode(seg)
                        model.insertNodeInto(child, parent, parent.getChildCount())
                        parent = child
                    else:
                        parent = found
                    lst = node_map.get(accum)
                    if lst is None: lst = []; node_map[accum]=lst
                    if entry not in lst: lst.append(entry)
                full_key = host + path
                lst2 = node_map.get(full_key)
                if lst2 is None: lst2 = []; node_map[full_key]=lst2
                if entry not in lst2: lst2.append(entry)

        try:
            self.tree_model = model
            self.node_map = node_map
            self.tree.setModel(self.tree_model)
            self.tree.setRootVisible(True)
            self._log("Site map indexed. Hosts: %d" % len(hosts))
        except Exception as e:
            self._err("apply model failed: " + str(e))

    # ---------------- UI Actions ----------------
    def _on_help(self, evt):
        help_text = (
            "APIHero - Quick Guide\n\n"
            "1) CTRL+Click to multi-select folders or endpoints.\n"
            "2) Click 'Load Selected' to preview extracted endpoints.\n"
            "3) Click 'Export CSV' to save grouped Method+URL CSV.\n"
            "   - Numeric/UUID path segments replaced with {id} placeholders."
        )
        JOptionPane.showMessageDialog(None, help_text)

    def _on_load_selected(self, evt):
        entries = [e for e in self._collect_entries_for_selected() if getattr(e,'getRequest',None) is not None]
        if not entries:
            self.preview.setText("No endpoints found.")
            return

        # Build grouped structure for preview
        grouped = {}
        total_count = 0
        for entry in entries:
            try:
                req = entry.getRequest()
                analyzed = self._helpers.analyzeRequest(req)
                url = str(analyzed.getUrl())
                method = analyzed.getMethod()
            except:
                try:
                    url = entry.getUrl().toString()
                    method = "GET"
                except:
                    continue

            host = url.split("/",3)[2] if "://" in url else "unknown_host"
            normalized = normalize_path_for_placeholders(url)
            segs = [s for s in normalized.split("/") if s]
            top_folder = segs[0] if segs else "/"
            grouped.setdefault(host, {}).setdefault(top_folder, []).append((method, normalized))

        # Build preview text
        preview_lines = []
        for host, folders in sorted(grouped.items()):
            preview_lines.append("Host: %s" % host)
            for folder, records in sorted(folders.items()):
                preview_lines.append("  Folder: %s (%d endpoints)" % (folder, len(records)))
                for method, ep in records:
                    preview_lines.append("    %s  %s" % (method, ep))
                    total_count += 1
        preview_text = "Endpoints Loaded: %d\n\n" % total_count + "\n".join(preview_lines)
        self.preview.setText(preview_text)

    # ---------------- CSV Export ----------------
    def _on_export_csv(self, evt):
        entries = [e for e in self._collect_entries_for_selected() if getattr(e,'getRequest',None) is not None]
        if not entries:
            JOptionPane.showMessageDialog(None,"No endpoints with requests to export.")
            return

        path = choose_file("apihero_export.csv")
        if not path: return

        # Build grouped structure
        grouped = {}
        for entry in entries:
            try:
                req = entry.getRequest()
                analyzed = self._helpers.analyzeRequest(req)
                url = str(analyzed.getUrl())
                method = analyzed.getMethod()
            except:
                try:
                    url = entry.getUrl().toString()
                    method = "GET"
                except:
                    continue

            host = url.split("/",3)[2] if "://" in url else "unknown_host"
            normalized = normalize_path_for_placeholders(url)
            segs = [s for s in normalized.split("/") if s]
            top_folder = segs[0] if segs else "/"
            grouped.setdefault(host, {}).setdefault(top_folder, []).append((method, normalized))

        # Write CSV following grouped order
        try:
            with open(path, "w") as f:
                f.write("Host,Top-Level Folder,Method,Endpoint\n")
                for host, folders in sorted(grouped.items()):
                    for folder, records in sorted(folders.items()):
                        for method, ep in records:
                            f.write('"%s","%s","%s","%s"\n' % (host, folder, method, ep))
            JOptionPane.showMessageDialog(None, "CSV exported successfully.\nSaved at:\n%s" % path)
        except Exception:
            self._err("CSV export failed:\n" + traceback.format_exc())
            JOptionPane.showMessageDialog(None,"CSV export failed: see stderr.")
