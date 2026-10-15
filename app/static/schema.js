/* Everything the form asks, in one place. Edit labels here and both the
   entry form and the records view pick them up. */

const SCHEMA = {
  sections: [
    { id: 'patient',   title: 'Patient',                    short: 'Patient',   hint: 'Who the intervention was for.' },
    { id: 'drug',      title: 'Drug and condition',         short: 'Drug',      hint: 'What drug or disease is involved.' },
    { id: 'problem',   title: 'Drug-related problem',       short: 'Problem',   hint: 'Select everything that applies. Add a short note if it helps.' },
    { id: 'action',    title: 'What you did',               short: 'Action',    hint: 'Who you contacted, what you reviewed and what you taught.' },
    { id: 'recommend', title: 'Recommendations',            short: 'Advice',    hint: 'What you recommended.' },
    { id: 'result',    title: 'Result of recommendation',   short: 'Result',    hint: 'Select all that apply.' },
    { id: 'outcome',   title: 'Time and expected outcome',  short: 'Outcome',   hint: '' },
    { id: 'signoff',   title: 'Sign-off',                   short: 'Sign-off',  hint: '' },
  ],
};

const FIELDS = {
  patient: [
    { k: 'date',     label: 'Date', type: 'date', req: true },
    { k: 'pharmacy', label: 'Pharmacy', req: true },
    { k: 'ward',     label: 'Ward' },
    { k: 'mrn',      label: 'Pharmacy MRN' },
    { k: 'initials', label: 'Patient initials', req: true },
    { k: 'age',      label: 'Age', ph: 'e.g. 54 or 6 months' },
    { k: 'gender',   label: 'Gender', type: 'select', options: ['Female', 'Male', 'Other'] },
    { k: 'weight',   label: 'Weight', ph: 'e.g. 70 kg' },
    { k: 'height',   label: 'Height', ph: 'e.g. 165 cm' },
    { k: 'labs',     label: 'Lab readings and other notes', type: 'textarea', wide: true, rows: 3 },
  ],
  drug: [
    { k: 'drug_name', label: 'Drug name', req: true },
    { k: 'disease',   label: 'Disease or condition' },
  ],
  specifics: { k: 'specifics', label: 'Intervention specifics', type: 'textarea', wide: true, rows: 5,
               ph: 'What you found, what you did and what you advised.',
               hint: 'About 550 characters fit in the box on the Excel form. The full text is always kept in the record.' },
  hours: { k: 'hours', label: 'Time spent (hours)', type: 'number', step: '0.05', min: '0', ph: 'e.g. 0.5' },
};

/* [id, label, optional note placeholder] */
const CHECKS = {
  problem: {
    prefix: 'drp_', cols: true,
    groups: [
      { title: 'Adverse drug reaction', items: [
        ['adr_toxicity', 'Toxicity'], ['adr_allergic', 'Allergic reaction'], ['adr_side', 'Side effect'] ] },
      { title: 'Drug choice', items: [
        ['choice_needed', 'Drug needed but not prescribed'],
        ['choice_inappropriate', 'Inappropriate drug according to guidelines'],
        ['choice_duplication', 'Drug duplication'],
        ['choice_cost', 'Cost of therapy'],
        ['choice_contra', 'Contraindication'],
        ['choice_form', 'Inappropriate dosage form'] ] },
      { title: 'Dosing', items: [
        ['dose_low', 'Dose too low or frequency inadequate'],
        ['dose_high', 'Dose too high or frequency too often'],
        ['dose_duration', 'Duration inappropriate'] ] },
      { title: 'Drug use', items: [
        ['use_wrongdose', 'Wrong dose administered'],
        ['use_wrongdrug', 'Wrong drug administered'],
        ['use_notgiven', 'Drug not given'],
        ['use_unavailable', 'Drug not available'],
        ['use_storage', 'Incorrect storage'],
        ['use_route', 'Incorrect route of administration'] ] },
      { title: 'Interaction', items: [
        ['int_drug', 'Drug\u2013drug'], ['int_disease', 'Drug\u2013disease'], ['int_food', 'Drug\u2013food'] ] },
      { title: 'Patient', items: [
        ['pt_instructions', "Patient didn't follow instructions"],
        ['pt_misuse', 'Patient misuse (over-use or under-use)'],
        ['pt_nonadherence', 'Non-adherence'] ] },
    ],
  },
  action: {
    prefix: 'act_', cols: true,
    groups: [
      { title: 'Drug', items: [['tdm', 'Therapeutic drug monitoring']] },
      { title: 'Prescriber or health care professional', items: [
        ['prescriber', 'Prescriber contacted', 'Who and how?'], ['pharmacy', 'Pharmacy contacted', 'Which pharmacy?'] ] },
      { title: 'Patient or caregiver', items: [
        ['dmp', 'Disease management programme'], ['regimen', 'Drug regimen review'], ['contacted', 'Patient contacted'] ] },
      { title: 'Education on', items: [
        ['edu_disease', 'Disease'], ['edu_adherence', 'Medication adherence'],
        ['edu_counsel', 'Counseling'], ['edu_other', 'Other'] ] },
      { title: 'Training', items: [
        ['train_device', 'Adherence device'], ['train_other', 'Other'] ] },
      { title: 'Lifestyle changes', items: [
        ['life_diet', 'Diet'], ['life_exercise', 'Exercise'],
        ['life_smoking', 'Smoking cessation'], ['life_alcohol', 'Alcohol moderation'] ] },
    ],
  },
  recommend: {
    prefix: 'rec_',
    groups: [ { title: null, items: [
      ['stop', 'Discontinue therapy'],
      ['change_med', 'Change medication', 'To what?'],
      ['add_rx', 'Add medication (Rx)', 'Which drug?'],
      ['add_otc', 'Add medication (OTC)', 'Which drug?'],
      ['change_dose', 'Change dose', 'New dose'],
      ['change_form', 'Change dosage form', 'New form'],
      ['change_interval', 'Change dosing interval', 'New interval'],
      ['tdm', 'Therapeutic drug monitoring'],
      ['education', 'Patient education or counseling'],
    ] } ],
  },
  result: {
    prefix: 'res_',
    groups: [ { title: null, items: [
      ['acc_prescriber', 'Accepted by prescriber'],
      ['acc_team', 'Accepted by consult team'],
      ['acc_patient', 'Accepted by patient or caregiver'],
      ['not_accepted', 'Not accepted by', 'Who, and why?'],
      ['unknown', 'Unknown'],
      ['other', 'Other', 'Details'],
    ] } ],
  },
  outcome: {
    prefix: 'out_',
    groups: [ { title: 'Expected outcome', items: [
      ['efficacy', 'Improved efficacy'],
      ['safety', 'Improved safety'],
      ['adherence', 'Improved adherence'],
      ['save_inst', 'Cost saving (institution)', 'Estimated amount'],
      ['save_pt', 'Cost saving (patient)', 'Estimated amount'],
    ] } ],
  },
};
