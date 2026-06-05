import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

export default function Devices() {
  return (
    <div className="flex-1 space-y-4 p-8 pt-6">
      <div className="flex items-center justify-between space-y-2">
        <h2 className="text-3xl font-bold tracking-tight">Audio Devices</h2>
      </div>
      
      <Card>
        <CardHeader>
          <CardTitle>Input Devices</CardTitle>
          <CardDescription>Configure audio input devices</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground">Audio input configuration will be available here.</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Output Devices</CardTitle>
          <CardDescription>Configure audio output devices</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground">Audio output configuration will be available here.</p>
        </CardContent>
      </Card>
    </div>
  )
}
