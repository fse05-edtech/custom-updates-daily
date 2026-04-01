(function() {
    function doKeycloakLogout() {
        var logoutUrl = 'http://172.26.197.98:8090/realms/platform/protocol/openid-connect/logout?redirect_uri=' + encodeURIComponent('http://172.26.197.98:8081/guacamole') + '&client_id=guacamole';
        fetch('/guacamole/api/tokens', { method: 'DELETE' }).catch(function(){});
        sessionStorage.clear();
        setTimeout(function() {
            window.location.href = logoutUrl;
        }, 200);
    }
    function interceptLogout() {
        document.addEventListener('click', function(e) {
            var el = e.target;
            for (var i = 0; i < 5; i++) {
                if (!el) break;
                var text = (el.textContent || el.innerText || '').trim().toLowerCase();
                var href = (el.getAttribute && el.getAttribute('href')) || '';
                if (text === 'logout' || text === 'sign out' || href.indexOf('logout') !== -1) {
                    e.preventDefault();
                    e.stopPropagation();
                    doKeycloakLogout();
                    return;
                }
                el = el.parentElement;
            }
        }, true);
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', interceptLogout);
    } else {
        interceptLogout();
    }
})();
