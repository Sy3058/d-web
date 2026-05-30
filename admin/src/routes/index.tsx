import { createFileRoute } from '@tanstack/react-router'

export const Route = createFileRoute('/')({
  component: Home,
})

function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-2">
      <h1 className="text-2xl font-bold">관리자 페이지</h1>
      <p className="text-gray-500">Vite + React + TanStack Router 골격</p>
    </main>
  )
}
