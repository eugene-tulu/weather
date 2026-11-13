"use client";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main className="min-h-screen grid place-items-center p-4">
      <div className="max-w-md space-y-3 text-center">
        <h1 className="text-2xl font-bold">Something went wrong</h1>
        <p className="text-sm text-muted-foreground">
          {error.message || "The forecast could not be rendered."}
        </p>
        <button
          type="button"
          onClick={reset}
          className="text-sm underline underline-offset-4 focus-visible:ring-2 focus-visible:ring-ring"
        >
          Try again
        </button>
      </div>
    </main>
  );
}
