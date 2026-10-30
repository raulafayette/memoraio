import AppKit
let path=CommandLine.arguments[1]
let sizes=[16,32,128,256,512]
try FileManager.default.createDirectory(atPath:path,withIntermediateDirectories:true)
for s in sizes { for scale in [1,2] {
    let px=s*scale
    let bitmap=NSBitmapImageRep(bitmapDataPlanes:nil,pixelsWide:px,pixelsHigh:px,bitsPerSample:8,samplesPerPixel:4,hasAlpha:true,isPlanar:false,colorSpaceName:.deviceRGB,bytesPerRow:0,bitsPerPixel:0)!
    NSGraphicsContext.saveGraphicsState();NSGraphicsContext.current=NSGraphicsContext(bitmapImageRep:bitmap)
    let n=CGFloat(px)
    NSColor(red:0.10,green:0.27,blue:0.24,alpha:1).setFill();NSBezierPath(roundedRect:NSRect(x:n*0.04,y:n*0.04,width:n*0.92,height:n*0.92),xRadius:n*0.22,yRadius:n*0.22).fill()
    // Original archive mark: two folios and three indexed bands; no SF Symbol artwork.
    NSColor(red:0.54,green:0.74,blue:0.65,alpha:1).setFill();NSBezierPath(roundedRect:NSRect(x:n*0.26,y:n*0.20,width:n*0.48,height:n*0.62),xRadius:n*0.055,yRadius:n*0.055).fill()
    NSColor(red:0.94,green:0.96,blue:0.90,alpha:1).setFill();NSBezierPath(roundedRect:NSRect(x:n*0.20,y:n*0.24,width:n*0.48,height:n*0.62),xRadius:n*0.055,yRadius:n*0.055).fill()
    NSColor(red:0.10,green:0.27,blue:0.24,alpha:1).setFill()
    for i in 0..<3 {NSBezierPath(roundedRect:NSRect(x:n*0.29,y:n*(0.64-CGFloat(i)*0.11),width:n*(i==2 ? 0.15:0.29),height:n*0.04),xRadius:n*0.02,yRadius:n*0.02).fill()}
    NSGraphicsContext.restoreGraphicsState()
    let name="icon_\(s)x\(s)"+(scale==2 ? "@2x":"")+".png"
    try bitmap.representation(using:.png,properties:[:])!.write(to:URL(fileURLWithPath:path).appendingPathComponent(name))
} }
