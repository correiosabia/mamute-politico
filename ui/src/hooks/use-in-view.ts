import * as React from 'react';

interface UseInViewOptions {
  rootMargin?: string;
  once?: boolean;
}

export function useInView(
  ref: React.RefObject<Element | null>,
  { rootMargin = '100px', once = true }: UseInViewOptions = {},
) {
  const [inView, setInView] = React.useState(false);

  React.useEffect(() => {
    const element = ref.current;
    if (!element) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setInView(true);
          if (once) {
            observer.disconnect();
          }
        } else if (!once) {
          setInView(false);
        }
      },
      { rootMargin },
    );

    observer.observe(element);
    return () => observer.disconnect();
  }, [ref, rootMargin, once]);

  return inView;
}
