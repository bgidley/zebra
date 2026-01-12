VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
  Persistable = 0  'NotPersistable
  DataBindingBehavior = 0  'vbNone
  DataSourceBehavior  = 0  'vbNone
  MTSTransactionMode  = 0  'NotAnMTSObject
END
Attribute VB_Name = "TaskDef"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = True
'/*
' * Copyright 2004 Anite - Central Government Division
' *    http://www.anite.com/publicsector
' *
' * Licensed under the Apache License, Version 2.0 (the "License");
' * you may not use this file except in compliance with the License.
' * You may obtain a copy of the License at
' *
' *    http://www.apache.org/licenses/LICENSE-2.0
' *
' * Unless required by applicable law or agreed to in writing, software
' * distributed under the License is distributed on an "AS IS" BASIS,
' * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
' * See the License for the specific language governing permissions and
' * limitations under the License.
' */
Option Explicit
Private mParentContainer As Container
Private WithEvents mContainer As Container
Attribute mContainer.VB_VarHelpID = -1
Private mInRouting As RoutingList
Private mOutRouting As RoutingList
Private mstrGUID As String
Private mPropertyGroup As PropertyGroup
Public TaskTemplate As String

Public Left As Single
Public Top As Single
Public Width As Single
Public Height As Single

Public Property Get GUID() As String
    GUID = mstrGUID
End Property

Public Property Let GUID(v As String)
    Dim OldGUID As String
    OldGUID = mstrGUID
    mstrGUID = v
    If Len(OldGUID) > 0 Then
        Tasks.ChangeGUID Me, OldGUID
    End If
    
End Property

Friend Property Set ParentContainer(v As Container)
    Set mParentContainer = v
End Property

Public Property Get Tasks() As Tasks
    Set Tasks = mParentContainer.GetParent
End Property

Private Sub Class_Initialize()
    Set mContainer = New Container
    
    Set mInRouting = New RoutingList
    Set mInRouting.ParentContainer = mContainer
    
    Set mOutRouting = New RoutingList
    Set mOutRouting.ParentContainer = mContainer
    
    Set mPropertyGroup = New PropertyGroup
    Dim oProps As Properties
    Set oProps = mPropertyGroup.Add(cSysPropGroup)
    
    With oProps
        .Add cPropName, vbNullString, ptString
        .Add "Synchronise", False, ptBoolean
        .Add "Auto", False, ptBoolean
        .Add "Class Name", vbNullString, ptString
        '.Add "Class Args", vbNullString, ptString
        .Add "NewThread", False, ptBoolean
    End With
    
End Sub

Public Property Get RoutingIn() As RoutingList
    Set RoutingIn = mInRouting
End Property

Public Property Get RoutingOut() As RoutingList
    Set RoutingOut = mOutRouting
End Property

Private Sub mContainer_GetMe(oReturn As Object)
    Set oReturn = Me
End Sub

Public Property Get PropertyGroup() As PropertyGroup
    Set PropertyGroup = mPropertyGroup
End Property

Public Property Get Name() As String
    Name = mPropertyGroup.Item(cSysPropGroup).Item(cPropName).Value
End Property

Public Property Let Name(v As String)
    mPropertyGroup.Item(cSysPropGroup).Item(cPropName).Value = v
End Property

Public Property Get Synchronise() As Boolean
    Synchronise = mPropertyGroup.Item(cSysPropGroup).Item("Synchronise").Value
End Property
Public Property Let Synchronise(v As Boolean)
    mPropertyGroup.Item(cSysPropGroup).Item("Synchronise").Value = v
End Property

