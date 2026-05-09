/* ============================================================
   EMS Pool Gamble — 全站共享 JS 工具
   - convertUtcToLocal: 把所有 [data-utc-time] 元素的 UTC 时间
     转成用户本地时间显示（兼容 iOS Chrome）。
   后续可继续追加 toast / fetch wrapper 等通用工具。
   ============================================================ */

(function () {
    'use strict';

    function convertUtcToLocal(root) {
        const scope = root || document;
        scope.querySelectorAll('[data-utc-time]').forEach(function (element) {
            const utcTime = element.getAttribute('data-utc-time');
            if (!utcTime || utcTime.trim() === '' || utcTime === '未知') return;

            try {
                let dateString = utcTime.trim();
                if (!dateString.includes('T') && !dateString.endsWith('Z') &&
                    !dateString.includes('+') && !dateString.includes(' UTC')) {
                    dateString = dateString.replace(' ', 'T') + 'Z';
                } else if (dateString.includes(' UTC')) {
                    dateString = dateString.replace(' UTC', 'Z').replace(' ', 'T');
                } else if (!dateString.endsWith('Z') && !dateString.includes('+') &&
                           !dateString.includes('-', 10)) {
                    dateString += 'Z';
                }

                const utcDate = new Date(dateString);
                if (!isNaN(utcDate.getTime())) {
                    element.textContent = utcDate.toLocaleString('zh-CN', {
                        year: 'numeric', month: '2-digit', day: '2-digit',
                        hour: '2-digit', minute: '2-digit', second: '2-digit'
                    });
                }
            } catch (e) {
                console.warn('时间转换失败:', utcTime, e);
            }
        });
    }

    // 暴露到全局，便于局部刷新后再次调用
    window.EMS = window.EMS || {};
    window.EMS.convertUtcToLocal = convertUtcToLocal;

    /* ---------- Toast 提示 ---------- */
    function ensureToastContainer() {
        let c = document.getElementById('ems-toast-container');
        if (!c) {
            c = document.createElement('div');
            c.id = 'ems-toast-container';
            c.style.cssText = 'position:fixed;top:1em;left:50%;transform:translateX(-50%);z-index:9999;display:flex;flex-direction:column;gap:0.5em;pointer-events:none;';
            document.body.appendChild(c);
        }
        return c;
    }
    function showToast(message, type) {
        type = type || 'success';
        const colors = {
            success: { bg: '#f6ffed', border: '#b7eb8f', color: '#52c41a' },
            error:   { bg: '#fff2f0', border: '#ffccc7', color: '#ff4d4f' },
            info:    { bg: '#e6f7ff', border: '#91d5ff', color: '#1890ff' }
        };
        const c = colors[type] || colors.info;
        const el = document.createElement('div');
        el.textContent = message;
        el.style.cssText = `background:${c.bg};border:1px solid ${c.border};color:${c.color};padding:10px 16px;border-radius:5px;font-size:0.95em;box-shadow:0 2px 8px rgba(0,0,0,0.1);pointer-events:auto;opacity:0;transform:translateY(-8px);transition:opacity .2s,transform .2s;max-width:90vw;`;
        ensureToastContainer().appendChild(el);
        requestAnimationFrame(() => { el.style.opacity = '1'; el.style.transform = 'translateY(0)'; });
        setTimeout(() => {
            el.style.opacity = '0';
            el.style.transform = 'translateY(-8px)';
            setTimeout(() => el.remove(), 250);
        }, 2200);
    }
    window.EMS.showToast = showToast;

    /* ---------- AJAX 表单提交 ----------
       用法：EMS.ajaxSubmit({ url, formData, onSuccess, onError })
       后端接口必须能识别 X-Requested-With: XMLHttpRequest 并返回
       { ok: true/false, message: string } 形式的 JSON。
    */
    async function ajaxSubmit(opts) {
        try {
            const res = await fetch(opts.url, {
                method: opts.method || 'POST',
                body: opts.formData,
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            });
            let data = null;
            try { data = await res.json(); } catch (_) { /* non-JSON */ }
            if (res.ok && data && data.ok) {
                if (opts.onSuccess) opts.onSuccess(data);
                else if (data.message) showToast(data.message, 'success');
            } else {
                const msg = (data && data.message) || `请求失败 (${res.status})`;
                if (opts.onError) opts.onError(msg, data);
                else showToast(msg, 'error');
            }
            return data;
        } catch (e) {
            const msg = '网络错误，请重试';
            if (opts.onError) opts.onError(msg, null);
            else showToast(msg, 'error');
            console.error('ajaxSubmit error:', e);
            return null;
        }
    }
    window.EMS.ajaxSubmit = ajaxSubmit;

    document.addEventListener('DOMContentLoaded', function () {
        convertUtcToLocal();
    });
})();
