import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Mic, Square, Play } from "lucide-react"

export default function Translate() {
  return (
    <div className="flex-1 space-y-4 p-8 pt-6">
      <div className="flex items-center justify-between space-y-2">
        <h2 className="text-3xl font-bold tracking-tight">Real-time Translation</h2>
      </div>
      
      <Card>
        <CardHeader>
          <CardTitle>Translation Controls</CardTitle>
          <CardDescription>Start and stop real-time audio translation</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex space-x-4">
            <Button size="lg">
              <Play className="mr-2 h-4 w-4" />
              Start Translation
            </Button>
            <Button variant="destructive" size="lg">
              <Square className="mr-2 h-4 w-4" />
              Stop Translation
            </Button>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Input</CardTitle>
            <CardDescription>Original audio/text</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-40 border-2 border-dashed rounded-lg flex items-center justify-center">
              <Mic className="h-8 w-8 text-muted-foreground" />
            </div>
          </CardContent>
        </Card>
        
        <Card>
          <CardHeader>
            <CardTitle>Output</CardTitle>
            <CardDescription>Translated audio/text</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-40 border-2 border-dashed rounded-lg flex items-center justify-center">
              <p className="text-muted-foreground">Translation will appear here</p>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
