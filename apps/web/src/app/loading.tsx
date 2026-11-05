import { LoadingIndicator } from '@/components/ui/loading-indicator';

export default function Loading() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <LoadingIndicator label="Loading SocietySphere..." size="lg" />
    </div>
  );
}
