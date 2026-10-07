import { useSyncExternalStore } from 'react';
import { Monitor, Moon, Sun } from 'lucide-react';
type ThemeChoice = 'light' | 'dark' | 'system';
declare global {
  interface Window { clientlaunchTheme: { getSnapshot: () => string; subscribe: (callback: () => void) => () => void; set: (choice: ThemeChoice) => void } }
}
export default function ThemeControl() {
  const snapshot = useSyncExternalStore(window.clientlaunchTheme.subscribe, window.clientlaunchTheme.getSnapshot, () => 'dark:dark');
  const [preference, resolved] = snapshot.split(':');
  const Icon = preference === 'system' ? Monitor : resolved === 'dark' ? Moon : Sun;
  return <label className="theme-control" title={`Appearance: ${preference}${preference === 'system' ? ` (${resolved})` : ''}`}>
    <Icon size={15} aria-hidden="true" /><span className="sr-only">Appearance</span>
    <select aria-label="Appearance" value={preference} onChange={event => window.clientlaunchTheme.set(event.target.value as ThemeChoice)}>
      <option value="light">Light</option><option value="dark">Dark</option><option value="system">System</option>
    </select>
  </label>;
}
