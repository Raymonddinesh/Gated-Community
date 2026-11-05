'use client';

import React, { useState, useEffect } from 'react';

export interface PageContainerProps {
  title?: string;
  subtitle?: string;
  children: React.ReactNode;
}

export const PageContainer: React.FC<PageContainerProps> = ({ title, subtitle, children }) => {
  const [mode, setMode] = useState<'standard' | 'easy' | 'admin'>('standard');

  useEffect(() => {
    const savedMode = (localStorage.getItem('societysphere_ui_mode') as 'standard' | 'easy' | 'admin') || 'standard';
    setMode(savedMode);
    document.body.setAttribute('data-mode', savedMode);
  }, []);

  const handleModeChange = (newMode: 'standard' | 'easy' | 'admin') => {
    setMode(newMode);
    localStorage.setItem('societysphere_ui_mode', newMode);
    document.body.setAttribute('data-mode', newMode);
  };

  return (
    <div className="min-h-screen flex flex-col bg-gray-50 text-gray-900 transition-colors duration-200">
      <header className="bg-white border-b border-gray-200 px-6 py-4 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-extrabold text-blue-700 tracking-tight">SocietySphere</h1>
          <p className="text-xs text-gray-500 font-medium">Enterprise Society Management</p>
        </div>

        {/* Experience Mode Switcher */}
        <div className="flex items-center gap-2" role="group" aria-label="Experience Mode">
          <span className="text-xs font-semibold text-gray-700 mr-1">Experience Mode:</span>
          <button
            onClick={() => handleModeChange('easy')}
            aria-pressed={mode === 'easy'}
            className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-colors border ${
              mode === 'easy' ? 'bg-black text-white border-black ring-2 ring-blue-500' : 'bg-gray-100 text-gray-800 border-gray-300 hover:bg-gray-200'
            }`}
          >
            Easy Mode (Elderly)
          </button>
          <button
            onClick={() => handleModeChange('standard')}
            aria-pressed={mode === 'standard'}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors border ${
              mode === 'standard' ? 'bg-blue-600 text-white border-blue-600' : 'bg-gray-100 text-gray-800 border-gray-300 hover:bg-gray-200'
            }`}
          >
            Standard
          </button>
          <button
            onClick={() => handleModeChange('admin')}
            aria-pressed={mode === 'admin'}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors border ${
              mode === 'admin' ? 'bg-gray-800 text-white border-gray-800' : 'bg-gray-100 text-gray-800 border-gray-300 hover:bg-gray-200'
            }`}
          >
            Admin / Pro
          </button>
        </div>
      </header>

      <main className="flex-1 max-w-7xl w-full mx-auto p-6 md:p-8">
        {(title || subtitle) && (
          <div className="mb-8">
            {title && <h2 className="text-2xl md:text-3xl font-bold text-gray-900 tracking-tight">{title}</h2>}
            {subtitle && <p className="mt-1 text-sm md:text-base text-gray-600">{subtitle}</p>}
          </div>
        )}
        {children}
      </main>

      <footer className="bg-white border-t border-gray-200 px-6 py-4 text-center text-xs text-gray-500">
        &copy; {new Date().getFullYear()} SocietySphere Platform. All rights reserved.
      </footer>
    </div>
  );
};
