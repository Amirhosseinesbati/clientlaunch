import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api, ApiError } from './lib/api';
import LoginScreen from './features/auth/LoginScreen';
import OperatorApp from './features/operator/OperatorApp';
import ClientPortal from './features/client/ClientPortal';
import { LoadingState } from './components/ui';

function isClientPath() {
  return window.location.pathname.startsWith('/client');
}

export default function App() {
  const [clientView, setClientView] = useState(isClientPath);
  const health = useQuery({ queryKey: ['health'], queryFn: api.health, refetchInterval: 30_000, retry: 1 });
  const session = useQuery({ queryKey: ['me'], queryFn: api.me, retry: false, enabled: !clientView });

  useEffect(() => {
    const onPopState = () => setClientView(isClientPath());
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  function navigate(path: '/client' | '/') {
    window.history.pushState({}, '', path);
    setClientView(path === '/client');
  }

  if (clientView) return <ClientPortal health={health.data} onOperator={() => navigate('/')} />;
  if (session.isPending) return <div className="app-loading"><LoadingState /></div>;
  if (session.data?.user) return <OperatorApp session={session.data} health={health.data} healthError={health.error} />;
  const connectionError = session.error instanceof ApiError && session.error.status !== 401 && session.error.status !== 403 ? session.error.message : undefined;
  return <LoginScreen health={health.data} onClientPortal={() => navigate('/client')} connectionError={connectionError} onRetryConnection={() => void session.refetch()} />;
}
