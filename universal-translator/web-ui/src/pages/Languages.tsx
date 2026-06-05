import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

export default function Languages() {
  return (
    <div className="flex-1 space-y-4 p-8 pt-6">
      <div className="flex items-center justify-between space-y-2">
        <h2 className="text-3xl font-bold tracking-tight">Language Settings</h2>
      </div>
      
      <Card>
        <CardHeader>
          <CardTitle>Source Language</CardTitle>
          <CardDescription>Configure the source language for translation</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground">Language selection will be available here.</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Target Language</CardTitle>
          <CardDescription>Configure the target language for translation</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground">Language selection will be available here.</p>
        </CardContent>
      </Card>
    </div>
  )
}
