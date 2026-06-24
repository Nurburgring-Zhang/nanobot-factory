import React, { useState } from 'react';
import { useLocalAuth } from '../../contexts/LocalAuthContext';
import { 
  Cpu,
  CheckCircle,
  AlertCircle,
  Loader2,
  RefreshCw,
  Wifi,
  WifiOff
} from 'lucide-react';

export const LocalAuth: React.FC = () => {
  const { connection, configs, connect, isLoading } = useLocalAuth();
  const [selectedConfig, setSelectedConfig] = useState('');

  const handleConnect = async () => {
    const config = configs.find(c => c.id === selectedConfig) || configs[0];
    if (config) {
      await connect(config);
    }
  };

  const getConnectionStatusIcon = () => {
    switch (connection.status) {
      case 'connected':
        return <CheckCircle className="w-5 h-5 text-green-400" />;
      case 'connecting':
        return <Loader2 className="w-5 h-5 animate-spin text-yellow-400" />;
      case 'error':
        return <AlertCircle className="w-5 h-5 text-red-400" />;
      default:
        return <WifiOff className="w-5 h-5 text-gray-400" />;
    }
  };

  const getConnectionStatusText = () => {
    switch (connection.status) {
      case 'connected':
        return '已连接到本地后端';
      case 'connecting':
        return '正在连接...';
      case 'error':
        return connection.error || '连接失败';
      default:
        return '未连接到本地后端';
    }
  };

  const getConnectionStatusColor = () => {
    switch (connection.status) {
      case 'connected':
        return 'text-green-400';
      case 'connecting':
        return 'text-yellow-400';
      case 'error':
        return 'text-red-400';
      default:
        return 'text-gray-400';
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-primary-900 via-primary-800 to-primary-700 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* 头部标题 */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-primary-600 rounded-full mb-4">
            <Cpu className="w-8 h-8 text-white" />
          </div>
          <h1 className="text-3xl font-bold text-white mb-2">General AIGC Enhanced</h1>
          <p className="text-neutral-300">本地化AIGC生成工具</p>
          
          {/* 连接状态指示器 */}
          <div className="mt-6 flex items-center justify-center space-x-3">
            {getConnectionStatusIcon()}
            <span className={`text-sm ${getConnectionStatusColor()}`}>
              {getConnectionStatusText()}
            </span>
          </div>
        </div>

        {/* 配置选择 */}
        {configs.length > 1 && (
          <div className="mb-6">
            <label className="block text-sm font-medium text-neutral-300 mb-2">
              选择后端服务
            </label>
            <select
              value={selectedConfig}
              onChange={(e) => setSelectedConfig(e.target.value)}
              className="w-full px-4 py-3 bg-primary-700/50 border border-primary-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-primary-500"
            >
              {configs.map((config) => (
                <option key={config.id} value={config.id}>
                  {config.name} - {config.backendUrl}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* 连接按钮 */}
        <button
          onClick={handleConnect}
          disabled={isLoading || connection.status === 'connecting'}
          className="w-full py-3 bg-primary-600 hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg font-medium transition-colors flex items-center justify-center space-x-2 mb-6"
        >
          {connection.status === 'connecting' ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : connection.status === 'connected' ? (
            <RefreshCw className="w-4 h-4" />
          ) : (
            <Wifi className="w-4 h-4" />
          )}
          <span>
            {connection.status === 'connecting' 
              ? '连接中...' 
              : connection.status === 'connected' 
                ? '重新连接' 
                : '连接后端服务'
            }
          </span>
        </button>

        {/* 功能介绍 */}
        <div className="p-4 bg-primary-800/30 rounded-lg border border-primary-700">
          <h3 className="text-lg font-semibold text-white mb-3 flex items-center space-x-2">
            <Cpu className="w-5 h-5" />
            <span>本地化AIGC功能</span>
          </h3>
          <ul className="space-y-2 text-sm text-neutral-300">
            <li className="flex items-center space-x-2">
              <CheckCircle className="w-4 h-4 text-green-400 flex-shrink-0" />
              <span>本地AI模型生成（无需云端依赖）</span>
            </li>
            <li className="flex items-center space-x-2">
              <CheckCircle className="w-4 h-4 text-green-400 flex-shrink-0" />
              <span>支持ComfyUI和WebUI集成</span>
            </li>
            <li className="flex items-center space-x-2">
              <CheckCircle className="w-4 h-4 text-green-400 flex-shrink-0" />
              <span>RTX4090 GPU硬件加速</span>
            </li>
            <li className="flex items-center space-x-2">
              <CheckCircle className="w-4 h-4 text-green-400 flex-shrink-0" />
              <span>图像、视频、3D生成</span>
            </li>
            <li className="flex items-center space-x-2">
              <CheckCircle className="w-4 h-4 text-green-400 flex-shrink-0" />
              <span>本地文件存储和管理</span>
            </li>
          </ul>
        </div>

        {/* 启动提示 */}
        {connection.status === 'error' && (
          <div className="mt-4 p-3 bg-red-900/30 border border-red-700 rounded-lg">
            <p className="text-red-300 text-sm">
              请先启动本地API服务器：python backend_api/main.py
            </p>
          </div>
        )}
      </div>
    </div>
  );
};