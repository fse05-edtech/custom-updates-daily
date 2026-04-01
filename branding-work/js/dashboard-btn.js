(function() {
    function isAdmin() {
        var links = document.querySelectorAll('ul.page-list-level.ng-scope li a');
        for (var i = 0; i < links.length; i++) {
            if (links[i].textContent.trim() === 'Users') return true;
        }
        return false;
    }

    function syncBtn() {
        var btn = document.getElementById('dash-btn');
        var admin = isAdmin();
        if (admin && !btn) {
            var ul = null;
            var allUls = document.querySelectorAll('ul.page-list-level.ng-scope');
            allUls.forEach(function(u) {
                u.querySelectorAll('a').forEach(function(a) {
                    if (a.textContent.trim() === 'Preferences') ul = u;
                });
            });
            if (ul) {
                var li = document.createElement('li');
                li.id = 'dash-btn';
                li.innerHTML = '<a onclick="openDashboard()" style="background:#2563eb;color:#fff;border-radius:6px;padding:5px 16px;font-weight:600;display:inline-block;text-decoration:none;cursor:pointer;">⚡ Dashboard</a>';
                ul.appendChild(li);
            }
        } else if (!admin && btn) {
            btn.remove();
        }
    }

    window.openDashboard = function() {
        var e = document.getElementById('dash-overlay');
        if (e) { e.remove(); return; }
        var w = document.createElement('div');
        w.id = 'dash-overlay';
        w.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;z-index:9999;background:#f5f7fa;';
        w.innerHTML = '<div style="padding:10px 16px;background:#fff;border-bottom:1px solid #e2e8f0;display:flex;align-items:center;gap:10px;"><button onclick="document.getElementById(\'dash-overlay\').remove()" style="background:#ef4444;color:#fff;border:none;border-radius:6px;padding:5px 14px;cursor:pointer;font-weight:600;">✕ Close</button><span style="font-weight:600;color:#0f172a;">⚡ Lab Access Dashboard</span></div><iframe src="/guacamole/dashboard.html" style="width:100%;height:calc(100% - 44px);border:none;"></iframe>';
        document.body.appendChild(w);
    };

    // Watch for DOM changes
    var observer = new MutationObserver(function() {
        syncBtn();
    });

    observer.observe(document.body, { childList: true, subtree: true });

    // Also run periodically as backup
    setInterval(syncBtn, 2000);
})();
