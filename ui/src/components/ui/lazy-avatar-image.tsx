import * as React from 'react';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { useInView } from '@/hooks/use-in-view';
import { cn } from '@/lib/utils';

interface LazyAvatarImageProps {
  src?: string;
  alt: string;
  fallback: React.ReactNode;
  className?: string;
}

export function LazyAvatarImage({ src, alt, fallback, className }: LazyAvatarImageProps) {
  const ref = React.useRef<HTMLSpanElement>(null);
  const inView = useInView(ref);

  if (inView) {console.log('in view', src)}

  return (
    <Avatar ref={ref} className={cn(className)}>
      <AvatarImage src={inView ? src : undefined} alt={alt} />
      <AvatarFallback>{fallback}</AvatarFallback>
    </Avatar>
  );
}
