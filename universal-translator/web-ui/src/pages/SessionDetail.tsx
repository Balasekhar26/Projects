import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { useParams } from "wouter"

export default function SessionDetail() {
  const params = useParams()
  const sessionId = params.id

  return (
    <div className="flex-1 space-y-4 p-8 pt-6">
      <div className="flex items-center justify-between space-y-2">
        <h2 className="text-3xl font-bold tracking-tight">Session {sessionId}</h2>
      </div>
      
      <Card>
        <CardHeader>
          <CardTitle>Session Details</CardTitle>
          <CardDescription>Detailed information about this translation session</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground">Session details for ID: {sessionId}</p>
        </CardContent>
      </Card>
    </div>
  )
}
