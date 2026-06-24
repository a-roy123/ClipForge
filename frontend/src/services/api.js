import axios from 'axios';

// Automatically normalizes the /api trailing suffix alignment with Docker/Nginx proxies
const rawBaseURL = import.meta.env.VITE_API_URL || 'http://localhost';
const baseURL = rawBaseURL.endsWith('/api') ? rawBaseURL : `${rawBaseURL}/api`;

const api = axios.create({
  baseURL,
  withCredentials: true, // Crucial for automatic HTTP-only refresh cookie routing
});

let memoryToken = null;

export const setInMemoryToken = (token) => {
  memoryToken = token;
};

export const getInMemoryToken = () => memoryToken;

// Interceptor to inject the active access token into outbound requests
api.interceptors.request.use(
  (config) => {
    if (memoryToken) {
      config.headers.Authorization = `Bearer ${memoryToken}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Interceptor to handle transparent silent JWT token refreshing on 401 expiration
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;
      try {
        const response = await axios.post(`${baseURL}/auth/refresh`, {}, { withCredentials: true });
        const { access_token } = response.data;
        setInMemoryToken(access_token);
        
        originalRequest.headers.Authorization = `Bearer ${access_token}`;
        return api(originalRequest);
      } catch (refreshError) {
        setInMemoryToken(null);
        return Promise.reject(refreshError);
      }
    }
    return Promise.reject(error);
  }
);

export default api;