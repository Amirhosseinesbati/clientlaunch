import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import { describe, expect, it } from 'vitest';
const source = readFileSync(new URL('../../public/theme-init.js', import.meta.url), 'utf8');
function boot(saved?: string, blocked = false) {
  const data = new Map(saved ? [['clientlaunch.theme', saved]] : []);
  const dataset: Record<string,string> = {};
  const changes = new Set<() => void>();
  const events: Record<string, (event: { key: string; newValue: string }) => void> = {};
  const media = { matches: false, addEventListener: (_type: string, callback: () => void) => changes.add(callback), removeEventListener: (_type: string, callback: () => void) => changes.delete(callback) };
  const context = { document: { documentElement: { dataset }, querySelector: () => ({ setAttribute: () => {} }) },
    localStorage: { getItem: (key: string) => { if (blocked) throw Error('blocked'); return data.get(key) ?? null; }, setItem: (key: string, value: string) => { if (blocked) throw Error('blocked'); data.set(key,value); } },
    window: { matchMedia: () => media, addEventListener: (type: string, callback: typeof events[string]) => { events[type]=callback; }, clientlaunchTheme: undefined as unknown as {set: (theme: string) => void; getSnapshot: () => string; subscribe: (callback: () => void) => () => void} }, Set };
  runInNewContext(source,context);
  return { ...context, dataset, changes, data, media, events, theme: context.window.clientlaunchTheme };
}
describe('pre-paint appearance runtime', () => {
  it('uses dark for a fresh or invalid preference and preserves a valid choice', () => {
    expect(boot().dataset.theme).toBe('dark'); expect(boot('invalid').dataset.theme).toBe('dark');
    expect(boot('light').theme.getSnapshot()).toBe('light:light'); expect(boot('system').theme.getSnapshot()).toBe('system:light');
  });
  it('persists deliberate choices without network or document remount', () => {
    const app=boot(); let count=0; app.theme.subscribe(()=>count++);
    app.theme.set('light'); expect(app.data.get('clientlaunch.theme')).toBe('light'); expect(app.dataset.theme).toBe('light');
    app.theme.set('light'); app.theme.set('invalid'); expect(count).toBe(1);
  });
  it('attaches OS following only to System and removes it for explicit modes', () => {
    const app=boot(); expect(app.changes.size).toBe(0); app.theme.set('system'); expect(app.changes.size).toBe(1);
    app.media.matches=true; app.changes.forEach(fn=>fn()); expect(app.dataset.theme).toBe('dark');
    app.theme.set('light'); expect(app.changes.size).toBe(0); app.media.matches=true; expect(app.dataset.theme).toBe('light');
  });
  it('works when storage reads and writes fail', () => {
    const app=boot('light',true); expect(app.dataset.theme).toBe('dark'); app.theme.set('light'); expect(app.dataset.theme).toBe('light');
  });
  it('accepts valid cross-tab choices and ignores corrupt data', () => {
    const app=boot(); app.events.storage!({ key:'clientlaunch.theme',newValue:'system' }); expect(app.changes.size).toBe(1);
    app.events.storage!({ key:'clientlaunch.theme',newValue:'garbage' }); expect(app.theme.getSnapshot()).toBe('system:light');
  });
});
