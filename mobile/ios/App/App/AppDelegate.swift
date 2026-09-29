import UIKit
import Capacitor

@UIApplicationMain
class AppDelegate: UIResponder, UIApplicationDelegate {

    var window: UIWindow?

    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        // Override point for customization after application launch.
        return true
    }

    func applicationWillResignActive(_ application: UIApplication) {
        // Sent when the application is about to move from active to inactive state. This can occur for certain types of temporary interruptions (such as an incoming phone call or SMS message) or when the user quits the application and it begins the transition to the background state.
        // Use this method to pause ongoing tasks, disable timers, and invalidate graphics rendering callbacks. Games should use this method to pause the game.
    }

    func applicationDidEnterBackground(_ application: UIApplication) {
        // Use this method to release shared resources, save user data, invalidate timers, and store enough application state information to restore your application to its current state in case it is terminated later.
        // If your application supports background execution, this method is called instead of applicationWillTerminate: when the user quits.
    }

    func applicationWillEnterForeground(_ application: UIApplication) {
        // Called as part of the transition from the background to the active state; here you can undo many of the changes made on entering the background.
    }

    func applicationDidBecomeActive(_ application: UIApplication) {
        // Restart any tasks that were paused (or not yet started) while the application was inactive. If the application was previously in the background, optionally refresh the user interface.
    }

    func applicationWillTerminate(_ application: UIApplication) {
        // Called when the application is about to terminate. Save data if appropriate. See also applicationDidEnterBackground:.
    }

    func application(_ application: UIApplication,
                     configurationForConnecting connectingSceneSession: UISceneSession,
                     options: UIScene.ConnectionOptions) -> UISceneConfiguration {
        let config = UISceneConfiguration(name: "Default Configuration",
                                          sessionRole: connectingSceneSession.role)
        config.delegateClass = SceneDelegate.self
        return config
    }
}

/// The app's web view, with BookPilot's own native plugins registered.
/// (Main.storyboard uses this class.)
class MainViewController: CAPBridgeViewController {
    override open func capacitorDidLoad() {
        bridge?.registerPluginInstance(PrintPlugin())
    }
}

/// WKWebView ignores window.print(), so receipts and invoices are printed
/// through AirPrint (or saved as PDF) from their HTML.
@objc(PrintPlugin)
public class PrintPlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "PrintPlugin"
    public let jsName = "BookPilotPrint"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "printHtml", returnType: CAPPluginReturnPromise)
    ]

    @objc func printHtml(_ call: CAPPluginCall) {
        guard let html = call.getString("html"), !html.isEmpty, html.count <= 2_000_000 else {
            call.reject("Nothing to print.")
            return
        }
        let jobName = call.getString("jobName") ?? "BookPilot"
        DispatchQueue.main.async {
            let info = UIPrintInfo(dictionary: nil)
            info.outputType = .general
            info.jobName = jobName
            let printer = UIPrintInteractionController.shared
            printer.printInfo = info
            printer.printFormatter = UIMarkupTextPrintFormatter(markupText: html)
            let done: UIPrintInteractionController.CompletionHandler = { _, completed, error in
                if let error = error {
                    call.reject(error.localizedDescription)
                } else {
                    call.resolve(["printed": completed])
                }
            }
            if UIDevice.current.userInterfaceIdiom == .pad, let view = self.bridge?.viewController?.view {
                let spot = CGRect(x: view.bounds.midX, y: view.bounds.midY, width: 1, height: 1)
                printer.present(from: spot, in: view, animated: true, completionHandler: done)
            } else {
                printer.present(animated: true, completionHandler: done)
            }
        }
    }
}
