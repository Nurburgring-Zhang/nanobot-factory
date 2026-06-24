import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import axios from 'axios';

export interface LocalConfig {
  id: string;
  name: string;
  backendUrl: string;
  isDefault?: boolean;
}

export interface LocalConnection {
  isConnected: boolean;
  status: 'connected' | 'disconnected' | 'connecting' | 'error';
  config: LocalConfig | null;
  error: string | null;
  serverInfo?: {
    version: string;
    models: string[];
    services: string[];
  };
}

interface LocalAuthContextType {
  connection: LocalConnection;
  configs: LocalConfig[];
  isLoading: boolean;
  connect: (config: LocalConfig) => Promise<boolean>;
  disconnect: () => void;
  saveConfig: (config: LocalConfig) => Promise<void>;
  deleteConfig: (id: string) => Promise<void>;
  setDefaultConfig: (id: string) => void;
  checkBackendHealth: (backendUrl?: string) => Promise<boolean>;
}

const LocalAuthContext = createContext<LocalAuthContextType | undefined>(undefined);

export const useLocalAuth = () => {
  const context = useContext(LocalAuthContext);
  if (!context) {
    throw new Error('useLocalAuth must be used within a LocalAuthProvider');
  }
  return context;
};

interface LocalAuthProviderProps {
  children: ReactNode;
}

export const LocalAuthProvider: React.FC<LocalAuthProviderProps> = ({ children }) => {
  const [connection, setConnection] = useState<LocalConnection>({
    isConnected: false,
    status: 'disconnected',
    config: null,
    error: null,
  });
  
  const [configs, setConfigs] = useState<LocalConfig[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  // 从localStorage加载保存的配置
  useEffect(() => {
    loadConfigs();
    setIsLoading(false);
  }, []);

  const loadConfigs = () => {
    try {
      const savedConfigs = localStorage.getItem('local_backend_configs');
      if (savedConfigs) {
        const parsed = JSON.parse(savedConfigs);
        setConfigs(parsed);
      } else {
        // 默认配置
        const defaultConfig: LocalConfig = {
          id: 'default',
          name: '本地后端服务',
          backendUrl: 'http://localhost:8000',
          isDefault: true,
        };
        setConfigs([defaultConfig]);
        localStorage.setItem('local_backend_configs', JSON.stringify([defaultConfig]));
      }
    } catch (error) {
      console.error('Failed to load local backend configs:', error);
    }
  };

  const saveConfigs = (newConfigs: LocalConfig[]) => {
    try {
      localStorage.setItem('local_backend_configs', JSON.stringify(newConfigs));
      setConfigs(newConfigs);
    } catch (error) {
      console.error('Failed to save local backend configs:', error);
      throw error;
    }
  };

  const checkBackendHealth = async (backendUrl: string): Promise<boolean> => {
    try {
      const response = await axios.get(`${backendUrl}/api/health`, {
        timeout: 5000,
      });
      return response.status === 200;
    } catch (error) {
      console.error('Backend health check failed:', error);
      return false;
    }
  };

  const connect = async (config: LocalConfig): Promise<boolean> => {
    setConnection(prev => ({ ...prev, status: 'connecting', error: null }));
    setIsLoading(true);
    
    try {
      // 测试后端连接
      const isHealthy = await checkBackendHealth(config.backendUrl);
      
      if (!isHealthy) {
        throw new Error(`无法连接到本地后端服务: ${config.backendUrl}`);
      }

      // 获取服务器信息
      const serverInfo = await getServerInfo(config.backendUrl);

      setConnection({
        isConnected: true,
        status: 'connected',
        config,
        error: null,
        serverInfo,
      });

      setIsLoading(false);
      return true;
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : '连接失败';
      setConnection({
        isConnected: false,
        status: 'error',
        config: null,
        error: errorMessage,
      });
      setIsLoading(false);
      return false;
    }
  };

  const getServerInfo = async (backendUrl: string) => {
    try {
      const response = await axios.get(`${backendUrl}/api/status`);
      return response.data;
    } catch (error) {
      console.warn('Failed to get server info:', error);
      return {
        version: '1.0.0',
        models: [],
        services: ['AI Generation'],
      };
    }
  };

  const disconnect = () => {
    setConnection({
      isConnected: false,
      status: 'disconnected',
      config: null,
      error: null,
    });
  };

  const saveConfig = async (config: LocalConfig): Promise<void> => {
    const newConfigs = [...configs];
    const existingIndex = newConfigs.findIndex(c => c.id === config.id);
    
    if (existingIndex >= 0) {
      newConfigs[existingIndex] = config;
    } else {
      newConfigs.push(config);
    }
    
    saveConfigs(newConfigs);
  };

  const deleteConfig = async (id: string): Promise<void> => {
    const newConfigs = configs.filter(c => c.id !== id);
    saveConfigs(newConfigs);
    
    // 如果删除的是当前连接的配置，则断开连接
    if (connection.config?.id === id) {
      disconnect();
    }
  };

  const setDefaultConfig = (id: string) => {
    const newConfigs = configs.map(config => ({
      ...config,
      isDefault: config.id === id,
    }));
    saveConfigs(newConfigs);
  };

  const value: LocalAuthContextType = {
    connection,
    configs,
    isLoading,
    connect,
    disconnect,
    saveConfig,
    deleteConfig,
    setDefaultConfig,
    checkBackendHealth,
  };

  return (
    <LocalAuthContext.Provider value={value}>
      {children}
    </LocalAuthContext.Provider>
  );
};