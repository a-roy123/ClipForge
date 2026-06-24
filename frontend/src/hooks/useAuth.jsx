import { useState, useEffect, createContext, useContext, useCallback } from 'react';
import api, { setInMemoryToken } from '../services/api';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const login = useCallback(async (email, password) => {
    // Sends standard JSON mapping your backend's UserLogin schema
    const response = await api.post('/auth/login', { email, password });
    const { access_token, user: userData } = response.data;
    
    setInMemoryToken(access_token);
    setUser(userData);
    return userData;
  }, []);

  const register = useCallback(async (username, email, password) => {
    const response = await api.post('/auth/register', { username, email, password });
    const { access_token, user: userData } = response.data;
    
    setInMemoryToken(access_token);
    setUser(userData);
    return userData;
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.post('/auth/logout');
    } catch (err) {
      console.error('Logout endpoint cleanup failed on host:', err);
    } finally {
      setInMemoryToken(null);
      setUser(null);
    }
  }, []);

  const checkAuthSilent = useCallback(async () => {
    try {
      // Rebuilds user session seamlessly on mount/refresh via the secure cookie bridge
      const response = await api.post('/auth/refresh');
      const { access_token, user: userData } = response.data;
      setInMemoryToken(access_token);
      setUser(userData);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    checkAuthSilent();
  }, [checkAuthSilent]);

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);