import React, { useEffect, useRef } from 'react';

export interface DialogProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: React.ReactNode;
}

export const Dialog: React.FC<DialogProps> = ({ isOpen, onClose, title, description, children }) => {
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    if (isOpen) {
      document.addEventListener('keydown', handleKeyDown);
      document.body.style.overflow = 'hidden';
    }
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = 'unset';
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="dialog-title"
      aria-describedby={description ? 'dialog-description' : undefined}
    >
      <div
        ref={dialogRef}
        className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl border border-gray-100 transition-all focus:outline-none"
        tabIndex={-1}
      >
        <div className="flex items-center justify-between pb-3 border-b border-gray-100">
          <h2 id="dialog-title" className="text-xl font-bold text-gray-900">
            {title}
          </h2>
          <button
            onClick={onClose}
            className="rounded-lg p-1 text-gray-400 hover:text-gray-700 hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-600"
            aria-label="Close dialog"
          >
            <span aria-hidden="true" className="text-xl font-bold">&times;</span>
          </button>
        </div>

        {description && (
          <p id="dialog-description" className="mt-2 text-sm text-gray-600">
            {description}
          </p>
        )}

        <div className="mt-4">{children}</div>
      </div>
    </div>
  );
};
