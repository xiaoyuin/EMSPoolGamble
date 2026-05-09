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

    document.addEventListener('DOMContentLoaded', function () {
        convertUtcToLocal();
    });
})();
