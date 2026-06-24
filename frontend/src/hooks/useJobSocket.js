import { useState, useEffect, useRef, useCallback } from 'react';
import { getInMemoryToken } from '../services/api';

export const useJobSocket = (jobId) => {
  const [jobData, setJobData] = useState(null);
  const [isConnected, setIsConnected] = useState(false);
  const socketRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const reconnectAttemptsRef = useRef(0);

  const connect = useCallback(() => {
    if (!jobId) return;

    if (socketRef.current) {
      socketRef.current.close();
    }

    const wsScheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
    // Targets the native non-proxied endpoint string: /ws/jobs/{job_id}
    const wsUrl = `${wsScheme}://${window.location.host}/ws/jobs/${jobId}`;

    const ws = new WebSocket(wsUrl);
    socketRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
      reconnectAttemptsRef.current = 0;
      
      // Fires token payload securely on frame transmission, preventing Nginx log exposure
      const token = getInMemoryToken();
      ws.send(JSON.stringify({ type: 'auth', token }));
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        setJobData(data);
      } catch (err) {
        console.error('Failed parsing incoming WebSocket frame data:', err);
      }
    };

    ws.onclose = (e) => {
      setIsConnected(false);
      socketRef.current = null;
      
      // Incremental Exponential Backoff Circuit Breaker
      if (e.code !== 1000) {
        const delay = Math.min(1000 * Math.pow(2, reconnectAttemptsRef.current), 30000);
        reconnectAttemptsRef.current += 1;
        
        reconnectTimeoutRef.current = setTimeout(() => {
          connect();
        }, delay);
      }
    };

    ws.onerror = (err) => {
      console.error('WebSocket interface fault encountered:', err);
      ws.close();
    };
  }, [jobId]);

  useEffect(() => {
    connect();
    return () => {
      if (socketRef.current) {
        socketRef.current.close(1000);
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, [connect]);

  return { jobData, isConnected };
};