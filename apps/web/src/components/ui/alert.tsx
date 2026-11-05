import React from 'react';

export interface AlertProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: 'info' | 'success' | 'warning' | 'error';
  title?: string;
}

export const Alert: React.FC<AlertProps> = ({ className = '', variant = 'info', title, children, ...props }) => {
  const styles = {
    info: 'bg-blue-50 border-blue-300 text-blue-900',
    success: 'bg-green-50 border-green-300 text-green-900',
    warning: 'bg-yellow-50 border-yellow-300 text-yellow-900',
    error: 'bg-red-50 border-red-300 text-red-900',
  };

  return (
    <div
      role={variant === 'error' ? 'alert' : 'status'}
      className={`rounded-lg border p-4 ${styles[variant]} ${className}`}
      {...props}
    >
      {title && <h4 className="font-bold text-sm mb-1">{title}</h4>}
      <div className="text-sm">{children}</div>
    </div>
  );
};
