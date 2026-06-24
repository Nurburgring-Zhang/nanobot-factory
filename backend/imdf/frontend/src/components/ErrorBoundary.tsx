/**
 * R3.5-W2 stub: 错误边界
 */
import type { ComponentType, ReactNode } from 'react';

interface ErrorBoundaryProps {
  fallbackTitle?: string;
  children?: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
}

const ErrorBoundary: ComponentType<ErrorBoundaryProps> = ({ children }) => {
  return <>{children}</>;
};

export default ErrorBoundary;
