import React from 'react';

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  modeVariant?: 'standard' | 'easy' | 'admin';
}

export const Card: React.FC<CardProps> = ({ className = '', modeVariant = 'standard', children, ...props }) => {
  const modeStyles = {
    standard: 'bg-white shadow-sm border border-gray-200 rounded-xl p-6',
    easy: 'bg-white border-2 border-black rounded-2xl p-8 shadow-none', // Easy Mode: clear black border, no subtle shadows
    admin: 'bg-white border border-gray-300 rounded-md p-4 shadow-none',
  };

  return (
    <div className={`${modeStyles[modeVariant]} ${className}`} {...props}>
      {children}
    </div>
  );
};

export const CardHeader: React.FC<React.HTMLAttributes<HTMLDivElement>> = ({ className = '', children, ...props }) => (
  <div className={`mb-4 pb-2 border-b border-gray-100 ${className}`} {...props}>
    {children}
  </div>
);

export const CardTitle: React.FC<React.HTMLAttributes<HTMLHeadingElement>> = ({ className = '', children, ...props }) => (
  <h3 className={`text-lg font-bold text-gray-900 tracking-tight ${className}`} {...props}>
    {children}
  </h3>
);

export const CardContent: React.FC<React.HTMLAttributes<HTMLDivElement>> = ({ className = '', children, ...props }) => (
  <div className={`space-y-4 ${className}`} {...props}>
    {children}
  </div>
);

export const CardFooter: React.FC<React.HTMLAttributes<HTMLDivElement>> = ({ className = '', children, ...props }) => (
  <div className={`mt-6 pt-4 border-t border-gray-100 flex items-center justify-end space-x-3 ${className}`} {...props}>
    {children}
  </div>
);
