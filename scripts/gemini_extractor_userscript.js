// ==UserScript==
// @name         Gemini to Claude Command Center (Antigravity)
// @namespace    http://tampermonkey.net/
// @version      1.1
// @description  Extracts Gemini conversations and sends them to local CCC for Antigravity continuation.
// @author       You
// @match        https://gemini.google.com/*
// @grant        GM_xmlhttpRequest
// @grant        GM_registerMenuCommand
// ==/UserScript==

(function() {
    'use strict';

    async function extractAndSend() {
        const btn = document.getElementById('ccc-export-btn');
        if (btn) {
            btn.innerText = 'Scrolling...';
            btn.disabled = true;
        }

        // Auto-scroll to the top to load all messages
        const scrollContainer = document.querySelector('infinite-scroller') || document.querySelector('cdk-virtual-scroll-viewport') || window;
        
        let lastHeight = 0;
        let retries = 0;
        
        while (retries < 5) {
            if (scrollContainer === window) {
                window.scrollTo(0, 0);
            } else {
                scrollContainer.scrollTop = 0;
            }
            
            await new Promise(r => setTimeout(r, 1000));
            
            const currentHeight = document.body.scrollHeight;
            if (currentHeight === lastHeight) {
                retries++;
            } else {
                retries = 0;
                lastHeight = currentHeight;
            }
        }

        if (btn) btn.innerText = 'Extracting...';
        
        // Extract messages. Gemini often uses <user-query> and <model-response>
        const messages = [];
        const elements = document.querySelectorAll('user-query, model-response');
        
        elements.forEach(el => {
            const role = el.tagName.toLowerCase() === 'user-query' ? 'USER_INPUT' : 'TEXT_RESPONSE';
            // Try to get clean text from inner content blocks
            const contentBlock = el.querySelector('.message-content') || el;
            messages.push({
                role: role,
                content: contentBlock.innerText || contentBlock.textContent
            });
        });

        // Fallback if the DOM has changed
        if (messages.length === 0) {
             const fallbackElements = document.querySelectorAll('[data-test-id="message"]');
             fallbackElements.forEach(el => {
                 const isUser = el.querySelector('img[alt*="profile"]') || el.innerText.trim().startsWith('You');
                 messages.push({
                     role: isUser ? 'USER_INPUT' : 'TEXT_RESPONSE',
                     content: el.innerText
                 });
             });
        }

        if (messages.length === 0) {
            alert('Could not find any messages in the DOM. Gemini UI might have changed.');
            if (btn) {
                btn.innerText = 'Failed';
                btn.disabled = false;
            }
            return;
        }

        if (btn) btn.innerText = 'Sending...';
        
        const payload = {
            title: document.title || 'Imported Gemini Chat',
            messages: messages
        };

        // Send to local CCC server
        try {
            const response = await fetch('http://127.0.0.1:8090/api/ingest/gemini', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const data = await response.json();
            if (btn) {
                btn.innerText = 'Sent! ' + data.session_id.substring(0, 8);
                setTimeout(() => { btn.innerText = 'Send to CCC'; btn.disabled = false; }, 3000);
            } else {
                alert('Successfully sent to CCC! Session ID: ' + data.session_id.substring(0, 8));
            }
            
        } catch (e) {
            console.error(e);
            alert('Failed to send to local server. Is CCC running on port 8090?');
            if (btn) {
                btn.innerText = 'Send to CCC';
                btn.disabled = false;
            }
        }
    }

    // 1. Register a Tampermonkey menu command as a foolproof fallback
    GM_registerMenuCommand("Extract Chat to CCC", extractAndSend);

    // 2. Try to inject a button, and use MutationObserver to keep it alive
    function injectButton() {
        if (document.getElementById('ccc-export-btn')) return;
        
        const btn = document.createElement('button');
        btn.id = 'ccc-export-btn';
        btn.innerText = 'Send to CCC';
        btn.style.position = 'fixed';
        btn.style.bottom = '20px';
        btn.style.right = '20px';
        btn.style.zIndex = '2147483647'; // Max z-index
        btn.style.padding = '10px 15px';
        btn.style.backgroundColor = '#D4A373';
        btn.style.color = '#fff';
        btn.style.border = 'none';
        btn.style.borderRadius = '5px';
        btn.style.cursor = 'pointer';
        btn.style.boxShadow = '0 2px 5px rgba(0,0,0,0.3)';
        btn.style.fontFamily = 'sans-serif';
        btn.style.fontSize = '14px';

        btn.addEventListener('click', extractAndSend);
        document.body.appendChild(btn);
    }

    // Initial injection
    injectButton();

    // Re-inject if Gemini's SPA routing clears the DOM
    const observer = new MutationObserver(() => {
        if (!document.getElementById('ccc-export-btn')) {
            injectButton();
        }
    });
    
    observer.observe(document.body, { childList: true, subtree: true });

})();
