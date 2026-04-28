// protocol_guard.js — Prevents external app protocol pop-ups.
// Injected before page load via Chrome --inject-js.

(function () {
  'use strict';

  const BLOCKED = /^(weixin|wechat|alipay|taobao|openapp|dianping|meituan|jd|tmall):\/\//i;

  // 1) Proxy window.location so assignments to non-HTTP(S) URLs are silently dropped.
  const realLocation = window.location;
  try {
    window.location = new Proxy(realLocation, {
      set(target, prop, value) {
        if (prop === 'href' && typeof value === 'string' && BLOCKED.test(value)) {
          console.log('[Guard] Blocked location.href:', value);
          return true;
        }
        target[prop] = value;
        return true;
      },
    });
  } catch (_e) {
    // Fallback for environments where Proxy is restricted
    Object.defineProperty(window, 'location', {
      configurable: false,
      get() {
        return realLocation;
      },
      set(url) {
        if (url && BLOCKED.test(String(url))) {
          console.log('[Guard] Blocked location:', url);
          return;
        }
        realLocation.href = url;
      },
    });
  }

  // 2) Wrap window.open
  const nativeOpen = window.open;
  window.open = function (url, target, features) {
    if (url && BLOCKED.test(String(url))) {
      console.log('[Guard] Blocked window.open:', url);
      return null;
    }
    return nativeOpen.apply(this, arguments);
  };

  // 3) Block clicks on links with external protocols (capture phase)
  document.addEventListener(
    'click',
    function (ev) {
      const anchor = ev.target.closest ? ev.target.closest('a[href]') : null;
      if (anchor && BLOCKED.test(anchor.href)) {
        console.log('[Guard] Blocked anchor:', anchor.href);
        ev.preventDefault();
        ev.stopPropagation();
      }
    },
    true
  );

  // 4) Wrap history pushState / replaceState for SPA routers that use protocols
  const wrapHistory = function (orig) {
    return function (state, title, url) {
      if (url && BLOCKED.test(String(url))) {
        console.log('[Guard] Blocked history navigation:', url);
        return;
      }
      return orig.apply(this, arguments);
    };
  };

  if (window.history) {
    if (window.history.pushState) {
      window.history.pushState = wrapHistory(window.history.pushState);
    }
    if (window.history.replaceState) {
      window.history.replaceState = wrapHistory(window.history.replaceState);
    }
  }

  // 5) MutationObserver: strip external-protocol hrefs from dynamically injected anchors
  const observer = new MutationObserver(function (mutations) {
    for (const m of mutations) {
      for (const node of m.addedNodes) {
        if (node.nodeType !== Node.ELEMENT_NODE) continue;
        const anchors = node.matches?.('a[href]') ? [node] : node.querySelectorAll?.('a[href]') || [];
        for (const a of anchors) {
          if (BLOCKED.test(a.href)) {
            a.removeAttribute('href');
            console.log('[Guard] Removed external protocol from injected anchor');
          }
        }
      }
    }
  });

  if (document.body) {
    observer.observe(document.body, { childList: true, subtree: true });
  } else {
    document.addEventListener('DOMContentLoaded', function () {
      if (document.body) observer.observe(document.body, { childList: true, subtree: true });
    });
  }

  console.log('[Guard] Protocol guard active');
})();
