import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

export default function Sessions() {
  return (
    <div className="flex-1 space-y-4 p-8 pt-6">
      <div className="flex items-center justify-between space-y-2">
        <h2 className="text-3xl font-bold tracking-tight">Translation Sessions</h2>
      </div>
      
      <Card>
        <CardHeader>
          <CardTitle>Session History</CardTitle>
          <CardDescription>View and manage past translation sessions</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground">No sessions yet. Start translating to see your history.</p>
        </CardContent>
      </Card>
    </div>
  )
}
