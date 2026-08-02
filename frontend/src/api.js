const BASE_URL = import.meta.env.VITE_API_BASE_URL || ''; // Uses environment variable in production, fallback to proxy for local dev.


// Helper to check if offline
const isOffline = () => !navigator.onLine;

// Retrieve auth token
const getToken = () => localStorage.getItem('token');

// API request helper with cache fallback for GET requests
export async function apiRequest(endpoint, options = {}) {
  const method = options.method || 'GET';
  const token = getToken();

  const headers = {
    'Content-Type': 'application/json',
    ...options.headers,
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const fetchOptions = {
    ...options,
    method,
    headers,
  };

  // Cache key isolated by token to prevent cross-tenant/store collision
  const tokenNs = token ? token.slice(-12) : 'public';
  const cacheKey = `api_cache:${tokenNs}:${endpoint}`;

  if (method === 'GET' && isOffline()) {
    const cached = localStorage.getItem(cacheKey);
    if (cached) {
      return { data: JSON.parse(cached), offline: true };
    }
    throw new Error("You are offline and this data is not cached.");
  }

  try {
    const response = await fetch(`${BASE_URL}${endpoint}`, fetchOptions);
    
    if (response.status === 401) {
      localStorage.removeItem('token');
      window.dispatchEvent(new Event('auth_failed'));
      const authErr = new Error("Unauthorized. Please login again.");
      authErr.status = 401;
      throw authErr;
    }
    
    if (response.status === 429) {
      const errData = await response.json();
      const limitErr = new Error(errData.detail || "Too many attempts. Please slow down.");
      limitErr.status = 429;
      throw limitErr;
    }

    const data = await response.json();

    if (!response.ok) {
      const apiErr = new Error(data.detail?.message || data.detail || "API Error");
      apiErr.status = response.status;
      throw apiErr;
    }

    // Cache successful GET requests
    if (method === 'GET') {
      try {
        localStorage.setItem(cacheKey, JSON.stringify(data));
      } catch (e) {
        console.warn("Storage quota exceeded, unable to cache api response", e);
      }
    }

    return { data, offline: false };
  } catch (error) {
    // Only fallback to cache on network connection errors or server 5xx errors, never on client 4xx validation errors
    if (method === 'GET' && (!error.status || error.status >= 500)) {
      const cached = localStorage.getItem(cacheKey);
      if (cached) {
        return { data: JSON.parse(cached), offline: true };
      }
    }
    throw error;
  }
}
