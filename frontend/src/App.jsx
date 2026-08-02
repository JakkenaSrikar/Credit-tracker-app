import React, { useState, useEffect } from 'react';
import { apiRequest } from './api';
import Login from './components/Login';
import Setup from './components/Setup';
import Dashboard from './components/Dashboard';
import CustomerDetail from './components/CustomerDetail';
import AddCustomer from './components/AddCustomer';
import AddTransaction from './components/AddTransaction';
import Settings from './components/Settings';
import ManageUsers from './components/ManageUsers';
import PinReset from './components/PinReset';
import QuickAdd from './components/QuickAdd';
import { LogOut, ShoppingBag, Wifi, WifiOff } from 'lucide-react';
import { translations } from './i18n';

export default function App() {
  const [screen, setScreen] = useState('loading'); 
  // 'loading' | 'setup' | 'login' | 'dashboard' | 'customer_detail' | 'add_customer' | 'add_transaction' | 'settings' | 'manage_users' | 'pin_reset' | 'quick_add'

  const [shopName, setShopName] = useState('');
  const [role, setRole] = useState('owner');
  const [language, setLanguage] = useState('en');
  const [storeId, setStoreId] = useState(null);
  const [userId, setUserId] = useState(null);

  const [selectedCustomerId, setSelectedCustomerId] = useState(null);
  const [txType, setTxType] = useState('credit');
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const [isOnline, setIsOnline] = useState(navigator.onLine);

  // Settings states
  const [darkMode, setDarkMode] = useState(localStorage.getItem('darkMode') === 'true');
  const [largeFont, setLargeFont] = useState(localStorage.getItem('largeFont') === 'true');

  // Offline queue state
  const [offlineQueue, setOfflineQueue] = useState([]);

  const t = translations[language];

  useEffect(() => {
    // Apply theme & font sizes on load
    if (darkMode) document.documentElement.classList.add('dark');
    if (largeFont) document.documentElement.classList.add('text-lg-mode');

    // Load initial offline queue from localStorage
    const savedQueue = JSON.parse(localStorage.getItem('offline_tx_queue') || '[]');
    setOfflineQueue(savedQueue);

    // Check connection changes
    const handleOnline = () => {
      setIsOnline(true);
      syncOfflineTransactions();
    };
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
  }, [language]);

  const checkSetupAndAuthStatus = async () => {
    try {
      const { data } = await apiRequest('/api/setup/status');
      if (data.setup_required) {
        setScreen('setup');
      } else {
        const token = localStorage.getItem('token');
        if (token) {
          // Verify current token by loading dashboard
          const dashboardRes = await apiRequest('/api/dashboard/summary');
          setShopName(dashboardRes.data.shop_name);
          setLanguage(dashboardRes.data.language || 'en');
          // Read credentials from localStorage if stored, or parse from JWT
          setRole(localStorage.getItem('user_role') || 'owner');
          setScreen('dashboard');
          
          // Trigger sync if online
          if (navigator.onLine) {
            syncOfflineTransactions();
          }
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

  const syncOfflineTransactions = async () => {
    const queue = JSON.parse(localStorage.getItem('offline_tx_queue') || '[]');
    if (queue.length === 0) return;
    
    let successCount = 0;
    let failedQueue = [];

    for (const tx of queue) {
      try {
        await apiRequest('/api/transactions', {
          method: 'POST',
          body: JSON.stringify(tx)
        });
        successCount++;
      } catch (e) {
        console.error("Failed to sync offline transaction", e);
        // Catch 404 (customer deleted in the meantime)
        if (e.message && e.message.includes("404")) {
          alert(`Sync failed: Customer for offline transaction no longer exists.`);
        } else {
          failedQueue.push(tx); // Keep it to retry later
        }
      }
    }

    localStorage.setItem('offline_tx_queue', JSON.stringify(failedQueue));
    setOfflineQueue(failedQueue);

    if (successCount > 0) {
      triggerDashboardRefresh();
      alert(translations[language].offline_sync_success);
    }
  };

  const handleLoginSuccess = (name, userRole, storeLang, store_id, user_id) => {
    setShopName(name);
    setRole(userRole);
    setLanguage(storeLang || 'en');
    setStoreId(store_id);
    setUserId(user_id);
    localStorage.setItem('user_role', userRole);
    setScreen('dashboard');
    if (navigator.onLine) syncOfflineTransactions();
  };

  const handleSetupSuccess = (name, userRole, storeLang, store_id, user_id) => {
    setShopName(name);
    setRole(userRole);
    setLanguage(storeLang || 'en');
    setStoreId(store_id);
    setUserId(user_id);
    localStorage.setItem('user_role', userRole);
    setScreen('dashboard');
  };

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user_role');
    setScreen('login');
  };

  const triggerDashboardRefresh = () => {
    setRefreshTrigger(prev => prev + 1);
  };

  const renderScreen = () => {
    switch (screen) {
      case 'setup':
        return <Setup language={language} onSetupSuccess={handleSetupSuccess} onBack={() => setScreen('login')} />;
      case 'login':
        return (
          <Login
            language={language}
            onLoginSuccess={handleLoginSuccess}
            onNavigateToSignup={() => setScreen('setup')}
            onNavigateToReset={() => setScreen('pin_reset')}
          />
        );
      case 'pin_reset':
        return <PinReset language={language} onBack={() => setScreen('login')} />;
      case 'dashboard':
        return (
          <Dashboard
            shopName={shopName}
            language={language}
            refreshTrigger={refreshTrigger}
            offlineQueueLength={offlineQueue.length}
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
            language={language}
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
      case 'settings':
        return (
          <Settings
            language={language}
            setLanguage={setLanguage}
            darkMode={darkMode}
            setDarkMode={setDarkMode}
            largeFont={largeFont}
            setLargeFont={setLargeFont}
            role={role}
            onBack={() => setScreen('dashboard')}
            onNavigate={(target) => setScreen(target)}
          />
        );
      case 'manage_users':
        return <ManageUsers language={language} onBack={() => setScreen('settings')} />;
      case 'quick_add':
        return (
          <QuickAdd
            language={language}
            onBack={() => setScreen('dashboard')}
            onTransactionSuccess={() => {
              triggerDashboardRefresh();
              setScreen('dashboard');
            }}
            offlineQueue={offlineQueue}
            setOfflineQueue={setOfflineQueue}
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

  const showHeader = screen !== 'loading' && screen !== 'login' && screen !== 'setup' && screen !== 'pin_reset';

  return (
    <div className={`min-h-screen bg-ledger-bg flex flex-col ${darkMode ? 'dark' : ''} ${largeFont ? 'text-lg-mode' : ''}`}>
      {/* Top Main Navigation Bar */}
      {showHeader && (
        <header className="bg-indigo-600 text-white shadow-md sticky top-0 z-20 select-none">
          <div className="max-w-md mx-auto px-4 py-3 flex justify-between items-center">
            <div className="flex items-center gap-2">
              <ShoppingBag className="w-5 h-5 text-indigo-200" />
              <h1 className="font-black text-lg tracking-tight">{t.title}</h1>
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
                className="p-1.5 hover:bg-indigo-700 active:bg-indigo-800 rounded-lg transition-colors flex items-center gap-1 text-sm font-semibold animate-fadeIn"
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
