/* Blocking same-origin script: CSP script-src 'self'; no inline styles, eval or business requests. */
(function () {
  'use strict';
  var key = 'clientlaunch.theme';
  var valid = function (value) { return value === 'light' || value === 'dark' || value === 'system'; };
  var preference = 'dark';
  try {
    var saved = localStorage.getItem(key);
    if (valid(saved)) preference = saved;
    else { var legacy = localStorage.getItem('clientlaunch_theme'); if (valid(legacy)) preference = legacy; }
  } catch (_) { /* Storage is optional; fresh visits use dark. */ }
  var media;
  try { media = window.matchMedia('(prefers-color-scheme: dark)'); } catch (_) { media = null; }
  var listeners = new Set();
  var following = false;
  var resolved;
  function apply() {
    resolved = preference === 'system' ? media && media.matches ? 'dark' : 'light' : preference;
    document.documentElement.dataset.theme = resolved;
    document.documentElement.dataset.themePreference = preference;
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute('content', resolved === 'dark' ? '#0b1018' : '#f4f7fa');
    if (media && preference === 'system' && !following) {
      if (media.addEventListener) media.addEventListener('change', onSystemChange);
      else if (media.addListener) media.addListener(onSystemChange);
      following = true;
    } else if (media && preference !== 'system' && following) {
      if (media.removeEventListener) media.removeEventListener('change', onSystemChange);
      else if (media.removeListener) media.removeListener(onSystemChange);
      following = false;
    }
  }
  function publish() { apply(); listeners.forEach(function (listener) { listener(); }); }
  function onSystemChange() { if (preference === 'system') publish(); }
  window.clientlaunchTheme = {
    getSnapshot: function () { return preference + ':' + resolved; },
    subscribe: function (listener) { listeners.add(listener); return function () { listeners.delete(listener); }; },
    set: function (value) {
      if (!valid(value) || value === preference) return;
      preference = value;
      try { localStorage.setItem(key, value); } catch (_) { /* Current tab still works. */ }
      publish();
    }
  };
  window.addEventListener('storage', function (event) {
    if (event.key === key && valid(event.newValue) && event.newValue !== preference) { preference = event.newValue; publish(); }
  });
  apply();
}());
