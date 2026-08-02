import React, { useState, useEffect } from 'react';
import { apiRequest } from './api';
import Login from './components/Login';
import Setup from './components/Setup';
import Dashboard from './components/Dashboard';
import CustomerDetail from './components/CustomerDetail';
import AddCustomer from './components/AddCustomer';
import AddTransaction from './components/AddTransaction';
import { LogOut, ShoppingBag, Wifi, WifiOff } from 'lucide-react';

export default function App() {
  const [screen, setScreen] = useState('loading'); // 'loading' | 'setup' | 'login' | 'dashboard' | 'customer_detail' | 'add_customer' | 'add_transaction'
  const [shopName, setShopName] = useState('');
  const [selectedCustomerId, setSelectedCustomerId] = useState(null);
  const [txType, setTxType] = useState('credit'); // 'credit' | 'payment'
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const [isOnline, setIsOnline] = useState(navigator.onLine);

  useEffect(() => {
    // Check connection changes
    const handleOnline = () => setIsOnline(true);
    const handleOffline = () => setIsOnline(false);
    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    // Handle token expired event from api.js
    const handleAuthFailed = () => {
      setScreen('login');
    };
    window.addEventListener('auth_failed', handleAuthFailed);

    checkSetupAndAuthStatus();

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
      window.removeEventListener('auth_failed', handleAuthFailed);
    };
  }, []);

  const checkSetupAndAuthStatus = async () => {
    try {
      const { data } = await apiRequest('/api/setup/status');
      if (data.setup_required) {
        setScreen('setup');
      } else {
        setShopName(data.shop_name);
        const token = localStorage.getItem('token');
        if (token) {
          setScreen('dashboard');
        } else {
          setScreen('login');
        }
      }
    } catch (e) {
      console.error("Initialization check failed", e);
      // Fallback: If offline and we have token, allow opening dashboard
      const token = localStorage.getItem('token');
      if (token) {
        setScreen('dashboard');
      } else {
        setScreen('login');
      }
    }
  };

  const handleLoginSuccess = (name) => {
    setShopName(name);
    setScreen('dashboard');
  };

  const handleSetupSuccess = (name) => {
    setShopName(name);
    setScreen('dashboard');
  };

  const handleLogout = () => {
    localStorage.removeItem('token');
    // Keep shop status, but drop to login
    setScreen('login');
  };

  const triggerDashboardRefresh = () => {
    setRefreshTrigger(prev => prev + 1);
  };

  const renderScreen = () => {
    switch (screen) {
      case 'setup':
        return <Setup onSetupSuccess={handleSetupSuccess} />;
      case 'login':
        return <Login onLoginSuccess={handleLoginSuccess} />;
      case 'dashboard':
        return (
          <Dashboard
            shopName={shopName}
            refreshTrigger={refreshTrigger}
            onSelectCustomer={(id) => {
              setSelectedCustomerId(id);
              setScreen('customer_detail');
            }}
            onNavigate={(target) => setScreen(target)}
          />
        );
      case 'customer_detail':
        return (
          <CustomerDetail
            customerId={selectedCustomerId}
            onBack={() => setScreen('dashboard')}
            onRefreshDashboard={triggerDashboardRefresh}
            onNavigateToAddTx={(type) => {
              setTxType(type);
              setScreen('add_transaction');
            }}
          />
        );
      case 'add_customer':
        return (
          <AddCustomer
            onBack={() => setScreen('dashboard')}
            onCustomerAdded={(newId) => {
              setSelectedCustomerId(newId);
              triggerDashboardRefresh();
              setScreen('customer_detail');
            }}
          />
        );
      case 'add_transaction':
        return (
          <AddTransaction
            customerId={selectedCustomerId}
            txType={txType}
            onBack={() => setScreen('customer_detail')}
            onTransactionSuccess={() => {
              triggerDashboardRefresh();
              setScreen('customer_detail');
            }}
          />
        );
      case 'loading':
      default:
        return (
          <div className="min-h-screen bg-ledger-bg flex flex-col items-center justify-center p-6">
            <div className="w-12 h-12 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin mb-4"></div>
            <p className="text-ledger-muted font-semibold text-sm">Opening Ledger Book...</p>
          </div>
        );
    }
  };

  const showHeader = screen !== 'loading' && screen !== 'login' && screen !== 'setup';

  return (
    <div className="min-h-screen bg-ledger-bg flex flex-col">
      {/* Top Main Navigation Bar */}
      {showHeader && (
        <header className="bg-indigo-600 text-white shadow-md sticky top-0 z-20 select-none">
          <div className="max-w-md mx-auto px-4 py-3 flex justify-between items-center">
            <div className="flex items-center gap-2">
              <ShoppingBag className="w-5 h-5 text-indigo-200" />
              <h1 className="font-black text-lg tracking-tight">Udhara Tracker</h1>
            </div>
            
            <div className="flex items-center gap-3">
              {/* Online/Offline Icon Indicator */}
              {isOnline ? (
                <Wifi className="w-4 h-4 text-green-300" title="Online" />
              ) : (
                <WifiOff className="w-4 h-4 text-red-300 animate-pulse" title="Offline" />
              )}
              
              <button
                onClick={handleLogout}
                className="p-1.5 hover:bg-indigo-700 active:bg-indigo-800 rounded-lg transition-colors flex items-center gap-1 text-sm font-semibold"
                title="Logout"
              >
                <LogOut className="w-4 h-4" />
                <span className="hidden sm:inline">Logout</span>
              </button>
            </div>
          </div>
        </header>
      )}

      {/* Main Container */}
      <main className="flex-1">
        {renderScreen()}
      </main>
    </div>
  );
}
