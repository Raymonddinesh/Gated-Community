import Link from 'next/link';

export default function NotFound() {
  return (
    <div className="min-h-screen flex items-center justify-center p-6 bg-gray-50">
      <div className="max-w-md w-full text-center bg-white p-8 rounded-2xl shadow-sm border border-gray-200">
        <h2 className="text-3xl font-extrabold text-blue-600 mb-2">404</h2>
        <h3 className="text-xl font-bold text-gray-900 mb-2">Page Not Found</h3>
        <p className="text-sm text-gray-600 mb-6">
          The requested resource could not be found or you may not have authorization to view it.
        </p>
        <Link
          href="/"
          className="inline-flex items-center justify-center font-medium rounded-lg px-4 py-2 bg-blue-600 text-white hover:bg-blue-700 transition-colors"
        >
          Return Home
        </Link>
      </div>
    </div>
  );
}
