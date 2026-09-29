package com.bookpilot.app;

import android.content.Context;
import android.print.PrintAttributes;
import android.print.PrintDocumentAdapter;
import android.print.PrintManager;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

/**
 * Android's WebView ignores window.print(), so receipts and invoices are
 * printed through the system print service (thermal printer apps, Wi-Fi
 * printers, Save as PDF...). The page HTML is rendered in an off-screen
 * WebView with scripts disabled and handed to PrintManager.
 */
@CapacitorPlugin(name = "BookPilotPrint")
public class PrintPlugin extends Plugin {

    private static final int MAX_HTML = 2_000_000;
    private WebView pending; // keeps the off-screen view alive until printing starts

    @PluginMethod
    public void printHtml(PluginCall call) {
        String html = call.getString("html");
        String baseUrl = call.getString("baseUrl");
        String jobName = call.getString("jobName", "BookPilot");
        if (html == null || html.isEmpty() || html.length() > MAX_HTML) {
            call.reject("Nothing to print.");
            return;
        }
        getActivity().runOnUiThread(() -> {
            WebView view = new WebView(getActivity());
            view.getSettings().setJavaScriptEnabled(false);
            view.setWebViewClient(new WebViewClient() {
                private boolean started = false;

                @Override
                public void onPageFinished(WebView webView, String url) {
                    if (started) return;
                    started = true;
                    try {
                        PrintManager manager = (PrintManager) getActivity().getSystemService(Context.PRINT_SERVICE);
                        PrintDocumentAdapter adapter = webView.createPrintDocumentAdapter(jobName);
                        manager.print(jobName, adapter, new PrintAttributes.Builder().build());
                        call.resolve();
                    } catch (Exception e) {
                        call.reject("Printing failed: " + e.getMessage());
                    } finally {
                        pending = null;
                    }
                }
            });
            pending = view;
            view.loadDataWithBaseURL(baseUrl, html, "text/html", "UTF-8", null);
        });
    }
}
