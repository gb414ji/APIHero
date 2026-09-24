# -*- coding: utf-8 -*-
# apihero.py - APIHero CSV Export (Jython 2.7) - auto-loads Target site map

from burp import IBurpExtender, ITab, IExtensionStateListener
from javax.swing import (JPanel, JScrollPane, JSplitPane, JButton, JTextArea,
                         JFileChooser, JOptionPane, JTree, SwingUtilities)
from javax.swing.tree import DefaultMutableTreeNode, DefaultTreeModel, TreeSelectionModel
from java.awt import BorderLayout, Dimension
from java.lang import Thread, Runnable
from java.io import File
import os, re, codecs, time, traceback

ID_RE = re.compile(r"(^|/)([0-9a-fA-F]{8,}|[0-9]+)(?=$|/)")


def normalize_path_for_placeholders(url):
    s = url
    if "://" in s:
        parts = s.split("/", 3)
        path = "/" + parts[3] if len(parts) >= 4 else "/"
    else:
        path = s
    path = path.split("?", 1)[0].split("#", 1)[0]
    path = ID_RE.sub(lambda m: m.group(1) + "{id}", path)
    path = re.sub("/+", "/", path)
    if path.endswith("/") and len(path) > 1:
        path = path[:-1]
    return path


def choose_file(default_name):
    try:
        fc = JFileChooser()
        fc.setSelectedFile(File(default_name))
        if fc.showSaveDialog(None) == JFileChooser.APPROVE_OPTION:
            return fc.getSelectedFile().getAbsolutePath()
        return None
    except:
        return os.path.join(os.path.expanduser("~"), default_name)


def csv_q(v):
    return u'"%s"' % (u"%s" % v).replace(u'"', u'""')


class Invoke(Runnable):
    def __init__(self, fn):
        self.fn = fn

    def run(self):
        try:
            self.fn()
        except:
            print(traceback.format_exc())


class Poller(Runnable):
    def __init__(self, ext):
        self.ext = ext

    def run(self):
        self.ext._poll_loop()


class BurpExtender(IBurpExtender, ITab, IExtensionStateListener):

    def registerExtenderCallbacks(self, callbacks):
        self._callbacks = callbacks
        self._helpers = callbacks.getHelpers()
        callbacks.setExtensionName("apihero")
        callbacks.registerExtensionStateListener(self)
        self.stdout = callbacks.getStdout()
        self.stderr = callbacks.getStderr()

        self.records = []       # (host, method, url)
        self.node_map = {}      # key -> [record indexes]
        self.node_keys = {}     # tree node -> key
        self._last_count = -1
        self._running = True

        self._build_ui()
        callbacks.addSuiteTab(self)

        t = Thread(Poller(self))
        t.setDaemon(True)
        t.start()
        self._log("apihero loaded. Auto-loading Target site map.")

    # ---- ITab / lifecycle ----
    def getTabCaption(self):
        return "APIHero"

    def getUiComponent(self):
        return self.panel

    def extensionUnloaded(self):
        self._running = False

    def _log(self, s):
        try:
            self.stdout.write(s + "\n"); self.stdout.flush()
        except:
            pass

    def _err(self, s):
        try:
            self.stderr.write(s + "\n"); self.stderr.flush()
        except:
            pass

    # ---- UI ----
    def _build_ui(self):
        root = DefaultMutableTreeNode("Site Map (loading...)")
        self.tree_model = DefaultTreeModel(root)
        self.tree = JTree(self.tree_model)
        self.tree.getSelectionModel().setSelectionMode(
            TreeSelectionModel.DISCONTIGUOUS_TREE_SELECTION)
        self.tree.setRootVisible(True)
        self.tree.setShowsRootHandles(True)

        self.panel = JPanel(BorderLayout())
        top = JPanel()
        self.btnRefresh = JButton("Refresh", actionPerformed=self._on_refresh)
        self.btnLoad = JButton("Load Selected", actionPerformed=self._on_load_selected)
        self.btnClear = JButton("Clear Selection", actionPerformed=self._on_clear_selection)
        self.btnCSV = JButton("Export CSV", actionPerformed=self._on_export_csv)
        self.btnUniqueCSV = JButton("Export Unique CSV", actionPerformed=self._on_export_unique_csv)
        self.btnHelp = JButton("Help", actionPerformed=self._on_help)
        for b in (self.btnRefresh, self.btnLoad, self.btnClear,
                  self.btnCSV, self.btnUniqueCSV, self.btnHelp):
            top.add(b)

        self.preview = JTextArea()
        self.preview.setEditable(False)
        self.preview.setLineWrap(True)
        self.preview.setWrapStyleWord(True)
        self.preview.setPreferredSize(Dimension(500, 400))

        split = JSplitPane(JSplitPane.HORIZONTAL_SPLIT,
                           JScrollPane(self.tree), JScrollPane(self.preview))
        split.setDividerLocation(350)
        self.panel.add(top, BorderLayout.NORTH)
        self.panel.add(split, BorderLayout.CENTER)

    # ---- Site map loading ----
    def _poll_loop(self):
        # first load immediately, then watch for changes
        first = True
        while self._running:
            try:
                self._refresh(force=first)
                first = False
            except:
                self._err("poll error:\n" + traceback.format_exc())
            for _ in range(6):          # ~3s, but exits quickly on unload
                if not self._running:
                    return
                time.sleep(0.5)

    def _fetch_records(self):
        try:
            entries = self._callbacks.getSiteMap(None)
        except Exception as e:
            self._err("getSiteMap failed: %s" % e)
            return []
        recs = []
        for e in entries:
            try:
                if e.getRequest() is None:
                    continue            # folder-only / unrequested node
                a = self._helpers.analyzeRequest(e)
                url = a.getUrl().toString()
                method = a.getMethod()
            except:
                continue
            host = url.split("/", 3)[2] if "://" in url else u"unknown_host"
            scheme = url.split("://", 1)[0] if "://" in url else "http"
            recs.append((scheme + u"://" + host, method, url))
        return recs

    def _refresh(self, force=False):
        # don't wipe the user's selection during auto-refresh
        if not force and self.tree.getSelectionCount() > 0:
            return
        recs = self._fetch_records()
        if not force and len(recs) == self._last_count:
            return
        self._last_count = len(recs)

        # build model off-EDT, apply on EDT
        root = DefaultMutableTreeNode("Site Map")
        model = DefaultTreeModel(root)
        node_map = {}
        node_keys = {root: u"__ALL__"}
        node_map[u"__ALL__"] = list(range(len(recs)))
        hosts = {}
        cache = {}

        for idx, (hostkey, method, url) in enumerate(recs):
            hnode = hosts.get(hostkey)
            if hnode is None:
                hnode = DefaultMutableTreeNode(hostkey)
                root.add(hnode)
                hosts[hostkey] = hnode
                node_keys[hnode] = hostkey
            node_map.setdefault(hostkey, []).append(idx)

            path = url.split("/", 3)[3] if url.count("/") >= 3 else u""
            path = path.split("?", 1)[0].split("#", 1)[0]
            parent = hnode
            accum = hostkey
            for seg in [s for s in path.split("/") if s]:
                accum = accum + u"/" + seg
                child = cache.get(accum)
                if child is None:
                    child = DefaultMutableTreeNode(seg)
                    parent.add(child)
                    cache[accum] = child
                    node_keys[child] = accum
                node_map.setdefault(accum, []).append(idx)
                parent = child

        def apply():
            self.records = recs
            self.node_map = node_map
            self.node_keys = node_keys
            self.tree_model = model
            self.tree.setModel(model)
            for i in range(min(self.tree.getRowCount(), 200)):
                self.tree.expandRow(i)
            self._log("Site map indexed: %d requests, %d hosts" % (len(recs), len(hosts)))

        SwingUtilities.invokeLater(Invoke(apply))

    # ---- Selection -> records ----
    def _selected_records(self):
        sel = self.tree.getSelectionPaths()
        if not sel:                      # nothing selected -> use everything
            return list(self.records)
        seen = set()
        out = []
        for p in sel:
            key = self.node_keys.get(p.getLastPathComponent())
            for idx in self.node_map.get(key, []):
                if idx not in seen:
                    seen.add(idx)
                    out.append(self.records[idx])
        return out

    def _group(self, recs, unique=False):
        grouped = {}
        seen = set()
        for hostkey, method, url in recs:
            host = hostkey.split("://", 1)[-1]
            ep = normalize_path_for_placeholders(url)
            if unique:
                if (host, method, ep) in seen:
                    continue
                seen.add((host, method, ep))
            segs = [s for s in ep.split("/") if s]
            top = segs[0] if segs else u"/"
            grouped.setdefault(host, {}).setdefault(top, []).append((method, ep))
        return grouped

    # ---- Actions ----
    def _on_refresh(self, evt):
        Thread(Invoke(lambda: self._refresh(force=True))).start()

    def _on_help(self, evt):
        JOptionPane.showMessageDialog(None,
            "APIHero - Quick Guide\n\n"
            "Target site map loads automatically (and refreshes every few seconds\n"
            "while nothing is selected).\n\n"
            "1) CTRL+Click to multi-select hosts/folders/endpoints.\n"
            "2) 'Load Selected' previews endpoints (no selection = everything).\n"
            "3) 'Clear Selection' deselects all.\n"
            "4) 'Export CSV' saves Host/Folder/Method/Endpoint.\n"
            "5) 'Export Unique CSV' saves de-duplicated normalized endpoints.\n"
            "6) 'Refresh' forces a reload from Target.")

    def _on_load_selected(self, evt):
        recs = self._selected_records()
        if not recs:
            self.preview.setText("No endpoints found. Browse the target through Burp, then click Refresh.")
            return
        grouped = self._group(recs)
        lines, total = [], 0
        for host, folders in sorted(grouped.items()):
            lines.append(u"Host: %s" % host)
            for folder, items in sorted(folders.items()):
                lines.append(u"  Folder: %s (%d endpoints)" % (folder, len(items)))
                for method, ep in items:
                    lines.append(u"    %s  %s" % (method, ep))
                    total += 1
        self.preview.setText(u"Endpoints Loaded: %d\n\n" % total + u"\n".join(lines))
        self.preview.setCaretPosition(0)

    def _on_export_csv(self, evt, unique=False):
        recs = self._selected_records()
        if not recs:
            JOptionPane.showMessageDialog(None, "No endpoints to export.")
            return
        path = choose_file("apihero_export.csv")
        if not path:
            return
        grouped = self._group(recs, unique=unique)
        try:
            f = codecs.open(path, "w", "utf-8")
            try:
                f.write(u"Host,Top-Level Folder,Method,Endpoint\n")
                for host, folders in sorted(grouped.items()):
                    for folder, items in sorted(folders.items()):
                        for method, ep in items:
                            f.write(u",".join([csv_q(host), csv_q(folder),
                                               csv_q(method), csv_q(ep)]) + u"\n")
            finally:
                f.close()
            JOptionPane.showMessageDialog(None, "CSV exported successfully.\nSaved at:\n%s" % path)
        except Exception:
            self._err("CSV export failed:\n" + traceback.format_exc())
            JOptionPane.showMessageDialog(None, "CSV export failed: see extension error output.")

    def _on_export_unique_csv(self, evt):
        self._on_export_csv(evt, unique=True)

    def _on_clear_selection(self, evt):
        self.tree.clearSelection()
        self.preview.setText("Selection cleared.")
