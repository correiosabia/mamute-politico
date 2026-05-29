export type CasaLegislativa = 'camara' | 'senado' | 'ambas';

export interface Partido {
  sigla: string;
  nome: string;
  cor?: string;
}

export interface GabineteDetalhes {
  predio?: string;
  sala?: string;
  andar?: string;
  nome?: string;
}

export interface RedeSocial {
  name: string;
  profileUrl?: string;
}

export interface Parlamentar {
  id: string;
  nome: string;
  nomeCompleto: string;
  foto: string;
  partido: Partido;
  uf: string;
  casa: CasaLegislativa;
  legislatura: number;
  email?: string;
  telefone?: string;
  gabinete?: string;
  gabineteDetalhes?: GabineteDetalhes;
  naturalidade?: string;
  escolaridade?: string;
  site?: string;
  emailGabinete?: string;
  biografiaLink?: string;
  biografiaTexto?: string;
  redesSociais?: RedeSocial[];
  situacao: 'Exercício' | 'Afastado' | 'Licenciado' | 'Fim de mandato';
}

export interface Proposicao {
  id: string;
  tipo: string;
  numero: number;
  ano: number;
  link?: string;
  ementa: string;
  dataApresentacao: string;
  situacao: string;
  tema: string;
  autor: string;
}

export interface Votacao {
  id: string;
  proposicao: string;
  proposicaoLink?: string;
  data: string;
  voto: 'Sim' | 'Não' | 'Abstenção' | 'Obstrução' | 'Ausente';
  descricao: string;
}

export interface Discurso {
  id: string;
  data: string;
  resumo: string;
  tema: string;
  palavrasChave: string[];
}

export interface Despesa {
  id: string;
  tipo: string;
  valor: number;
  mes: number;
  ano: number;
  fornecedor: string;
}

export interface ParlamentarMonitorado extends Parlamentar {
  dataAdicao: string;
}
