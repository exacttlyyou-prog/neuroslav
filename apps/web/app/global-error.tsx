'use client'

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  return (
    <html lang="ru">
      <body>
        <div className="flex min-h-screen flex-col items-center justify-center p-4">
          <div className="max-w-md w-full space-y-4 text-center">
            <h1 className="text-2xl font-bold text-red-600">Критическая ошибка</h1>
            <p className="text-gray-600">
              {error.message || 'Произошла критическая ошибка приложения'}
            </p>
            {error.digest && (
              <p className="text-sm text-gray-400">ID ошибки: {error.digest}</p>
            )}
            <button
              onClick={reset}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
            >
              Перезагрузить приложение
            </button>
          </div>
        </div>
      </body>
    </html>
  )
}
