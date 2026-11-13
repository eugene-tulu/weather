import Link from "next/link";

export default function NotFound() {
  return (
    <main className="min-h-screen grid place-items-center p-4">
      <div className="max-w-md space-y-3 text-center">
        <h1 className="text-2xl font-bold">Page not found</h1>
        <p className="text-sm text-muted-foreground">
          The page you were looking for does not exist.
        </p>
        <Link
          href="/"
          className="inline-block text-sm underline underline-offset-4 focus-visible:ring-2 focus-visible:ring-ring"
        >
          Back to the forecast
        </Link>
      </div>
    </main>
  );
}
