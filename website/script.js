(() => {
  const languageButton = document.querySelector('.language-button');
  const toast = document.querySelector('#toast');
  const copyButton = document.querySelector('#copyCommand');
  const dockDemo = document.querySelector('#dockDemo');
  const themeDemo = document.querySelector('#themeDemo');
  const themeName = document.querySelector('#themeName');
  let language = 'pt';
  let toastTimer;

  const words = {
    pt: {
      title: 'Orla Desktop — seu espaço, à sua maneira',
      description: 'Orla Desktop — um dock nativo, personalizável e aberto para o KDE Plasma.',
      copy: 'Copiado para a área de transferência.',
      copyError: 'Não foi possível copiar. Selecione o comando para copiar.',
      copiedButton: 'Copiado',
      copyButton: 'Copiar',
      midnight: 'MEIA-NOITE', glass: 'VIDRO', paper: 'PAPEL',
      toEnglish: 'Mudar idioma para inglês', toPortuguese: 'Change language to Portuguese'
    },
    en: {
      title: 'Orla Desktop — your space, your way',
      description: 'Orla Desktop — a native, customizable, open dock for KDE Plasma.',
      copy: 'Copied to clipboard.',
      copyError: 'Could not copy. Select the command and copy it manually.',
      copiedButton: 'Copied',
      copyButton: 'Copy',
      midnight: 'MIDNIGHT', glass: 'GLASS', paper: 'PAPER',
      toEnglish: 'Mudar idioma para inglês', toPortuguese: 'Change language to Portuguese'
    }
  };

  function showToast(message) {
    toast.textContent = message;
    toast.classList.add('visible');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove('visible'), 2600);
  }

  function setLanguage(next) {
    language = next;
    document.documentElement.lang = next === 'pt' ? 'pt-BR' : 'en';
    document.title = words[next].title;
    document.querySelector('meta[name="description"]').content = words[next].description;
    document.querySelectorAll('[data-pt][data-en]').forEach((element) => {
      if (element.hasAttribute('data-pt-aria')) return;
      element.innerHTML = element.dataset[next];
    });
    document.querySelectorAll('[data-pt-aria][data-en-aria]').forEach((element) => {
      element.setAttribute('aria-label', element.dataset[`${next}Aria`]);
    });
    document.querySelectorAll('[data-pt-href][data-en-href]').forEach((element) => {
      element.href = element.dataset[`${next}Href`];
    });
    themeName.textContent = words[next][themeDemo.dataset.theme];
    languageButton.setAttribute('aria-label', next === 'pt' ? words.pt.toEnglish : words.en.toPortuguese);
    copyButton.setAttribute('aria-label', words[next].copyButton);
    copyButton.title = words[next].copyButton;
    languageButton.setAttribute('aria-pressed', String(next === 'en'));
  }

  languageButton.addEventListener('click', () => setLanguage(language === 'pt' ? 'en' : 'pt'));

  document.querySelectorAll('[data-theme-choice]').forEach((button) => {
    button.addEventListener('click', () => {
      const selected = button.dataset.themeChoice;
      dockDemo.dataset.theme = selected;
      themeDemo.dataset.theme = selected;
      themeName.textContent = words[language][selected];
      document.querySelectorAll('[data-theme-choice]').forEach((option) => {
        option.setAttribute('aria-pressed', String(option === button));
      });
    });
  });

  copyButton.addEventListener('click', async () => {
    const command = document.querySelector('#installCommand').textContent;
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(command);
      } else {
        const input = document.createElement('textarea');
        input.value = command;
        input.setAttribute('readonly', '');
        input.style.position = 'fixed';
        input.style.opacity = '0';
        document.body.append(input);
        input.select();
        const copied = document.execCommand('copy');
        input.remove();
        if (!copied) throw new Error('Clipboard unavailable');
      }
      copyButton.querySelector('.copy-label').textContent = words[language].copiedButton;
      showToast(words[language].copy);
      setTimeout(() => {
        copyButton.querySelector('.copy-label').textContent = words[language].copyButton;
      }, 2200);
    } catch {
      showToast(words[language].copyError);
    }
  });

  setLanguage('pt');
})();
