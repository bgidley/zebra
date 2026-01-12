VERSION 5.00
Begin VB.Form frmVersions 
   BorderStyle     =   3  'Fixed Dialog
   Caption         =   "Select Version"
   ClientHeight    =   2655
   ClientLeft      =   45
   ClientTop       =   330
   ClientWidth     =   3705
   ControlBox      =   0   'False
   BeginProperty Font 
      Name            =   "Tahoma"
      Size            =   8.25
      Charset         =   0
      Weight          =   400
      Underline       =   0   'False
      Italic          =   0   'False
      Strikethrough   =   0   'False
   EndProperty
   LinkTopic       =   "Form1"
   MaxButton       =   0   'False
   MinButton       =   0   'False
   ScaleHeight     =   2655
   ScaleWidth      =   3705
   ShowInTaskbar   =   0   'False
   StartUpPosition =   3  'Windows Default
   Begin VB.CheckBox chkUpdate 
      Caption         =   "Open for Update"
      Height          =   255
      Left            =   2040
      TabIndex        =   3
      ToolTipText     =   "If this option is checked you will not be able to remove Tasks or Routing lines."
      Top             =   1560
      Width           =   1575
   End
   Begin VB.CommandButton cmdOK 
      Caption         =   "OK"
      Height          =   495
      Left            =   2040
      TabIndex        =   2
      Top             =   2040
      Width           =   1575
   End
   Begin VB.ListBox lst 
      Height          =   2010
      Left            =   240
      TabIndex        =   0
      Top             =   480
      Width           =   1455
   End
   Begin VB.Label lbl 
      AutoSize        =   -1  'True
      Caption         =   "Please select a Version to load"
      Height          =   195
      Left            =   240
      TabIndex        =   1
      Top             =   120
      Width           =   2175
   End
End
Attribute VB_Name = "frmVersions"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = True
Attribute VB_Exposed = False
Option Explicit
Public forUpdate As Boolean

Public Function showVersions(oVersions As Versions) As ProcessVersion
    lst.Clear
    chkUpdate.Value = vbUnchecked
    Dim v As ProcessVersion
    For Each v In oVersions
        lst.AddItem v.version
    Next
    lst.ListIndex = lst.ListCount - 1
    Me.Show vbModal
    '/ code stops here until form is hidden
    forUpdate = (chkUpdate.Value = vbChecked)
    Set showVersions = oVersions.Item(lst.List(lst.ListIndex))
    Unload Me
End Function

Private Sub cmdOK_Click()
    Me.Hide
End Sub


